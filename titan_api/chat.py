"""
Titan Core - Chat API
---------------------

Purpose:
    Handles chat requests for Titan.

Flow:
    1. Accept chat request
    2. Resolve temporary MVP user
    3. Save explicit memory requests directly
    4. Auto-detect personal facts to remember
    5. Search memory before AI fallback
    6. Check rule-based actions before brain fallback
    7. Return reply and any proposed actions
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from titan_core.db import get_db
from titan_core.schemas import BrainInput, ChatMessage
from titan_api.models import User, MemoryItem
from titan_api.schemas import ChatRequest, ChatResponse
from titan_core.brain import run_brain
from titan_core.rules import propose_actions

router = APIRouter()


# -----------------------------
# Memory Trigger Phrases
# -----------------------------

MEMORY_SAVE_TRIGGERS = [
    "remember that",
    "remember this",
    "titan remember",
    "hey titan remember",
    "save this",
    "store this",
]

AUTO_MEMORY_PREFIXES = [
    "i park",
    "i work",
    "i live",
    "i usually",
    "my wife",
    "my husband",
    "my daughter",
    "my son",
    "my dog",
    "my cat",
    "my favorite",
]

QUESTION_STARTERS = (
    "what ",
    "where ",
    "when ",
    "why ",
    "how ",
    "who ",
    "which ",
    "do ",
    "does ",
    "did ",
    "is ",
    "are ",
    "can ",
    "could ",
    "would ",
    "should ",
)


# -----------------------------
# Text Utilities
# -----------------------------


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def tokenize(text: str) -> set[str]:
    words = re.findall(r"\w+", normalize_text(text))
    return {word for word in words if len(word) > 2}


# -----------------------------
# Memory Detection / Scoring
# -----------------------------


def is_memory_save_request(text: str) -> bool:
    lowered = normalize_text(text)
    return any(trigger in lowered for trigger in MEMORY_SAVE_TRIGGERS)


def should_auto_remember(text: str) -> bool:
    lowered = normalize_text(text)

    if not lowered:
        return False

    if lowered.endswith("?"):
        return False

    if lowered.startswith(QUESTION_STARTERS):
        return False

    return any(lowered.startswith(prefix) for prefix in AUTO_MEMORY_PREFIXES)


def memory_importance_score(text: str) -> int:
    """
    Lightweight heuristic for deciding whether a message is worth storing.
    Higher score = more likely to be personal and useful later.
    """
    lowered = normalize_text(text)

    if not lowered:
        return 0

    score = 0

    personal_markers = [
        "i ",
        "my ",
        "we ",
        "our ",
    ]
    if any(lowered.startswith(marker) for marker in personal_markers):
        score += 1

    useful_keywords = [
        "park",
        "live",
        "work",
        "class",
        "school",
        "wife",
        "husband",
        "daughter",
        "son",
        "dog",
        "cat",
        "favorite",
        "usually",
        "always",
        "never",
        "play",
        "plays",
        "soccer",
    ]
    if any(word in lowered for word in useful_keywords):
        score += 1

    if len(lowered.split()) >= 5:
        score += 1

    if lowered.endswith("?"):
        score -= 2

    if lowered.startswith(QUESTION_STARTERS):
        score -= 2

    command_starters = (
        "open ",
        "launch ",
        "start ",
        "create ",
        "draft ",
        "help ",
        "remember ",
        "save ",
        "store ",
    )
    if lowered.startswith(command_starters):
        score -= 2

    return max(score, 0)


def extract_memory_content(text: str) -> str:
    if not text:
        return ""

    cleaned = text.strip()

    patterns = [
        r"(?i)^hey titan remember that\s*",
        r"(?i)^titan remember that\s*",
        r"(?i)^remember that\s*",
        r"(?i)^hey titan remember\s*",
        r"(?i)^titan remember\s*",
        r"(?i)^remember this\s*",
        r"(?i)^save this\s*",
        r"(?i)^store this\s*",
    ]

    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned).strip()

    return cleaned


# -----------------------------
# User Resolution
# -----------------------------


def get_default_mvp_user(db: Session) -> User:
    user = db.query(User).filter(User.username == "ron").first()
    if not user:
        raise RuntimeError("Default user not found. Run /seed first.")
    return user


# -----------------------------
# Memory Storage / Retrieval
# -----------------------------


def find_duplicate_memory(
    db: Session,
    user_id: int,
    tag: str,
    content: str,
) -> MemoryItem | None:
    normalized_new = normalize_text(content)

    rows = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user_id, MemoryItem.tag == tag)
        .order_by(MemoryItem.id.desc())
        .all()
    )

    for row in rows:
        if normalize_text(row.content) == normalized_new:
            return row

    return None


def create_memory(
    db: Session,
    user_id: int,
    tag: str,
    content: str,
    score: int = 1,
) -> MemoryItem:
    memory = MemoryItem(
        user_id=user_id,
        tag=tag,
        content=content,
        score=score,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def find_memory_match(db: Session, user_id: int, text: str) -> MemoryItem | None:
    query_words = tokenize(text)

    if not query_words:
        return None

    rows = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user_id)
        .order_by(MemoryItem.id.desc())
        .all()
    )

    best_row = None
    best_score = 0

    for row in rows:
        memory_words = tokenize(row.content)
        overlap = len(query_words & memory_words)

        if overlap > best_score:
            best_row = row
            best_score = overlap

    return best_row


# -----------------------------
# Brain Input Builder
# -----------------------------


def build_brain_input(
    db: Session,
    user: User,
    req: ChatRequest,
    clean_text: str,
) -> BrainInput:
    allowed_modes = {
        "personal_general",
        "personal_productivity",
        "personal_builder",
        "personal_family",
    }

    safe_mode = req.mode if req.mode in allowed_modes else "personal_general"

    memories = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user.id)
        .order_by(MemoryItem.id.desc())
        .limit(5)
        .all()
    )

    memory_text = ""

    if memories:
        memory_text = "Known facts about the user:\n"
        for m in memories:
            memory_text += f"- {m.content}\n"

    return BrainInput(
        user_id=user.id,
        role=user.role,
        mode=safe_mode,
        tools=[],
        messages=[
            ChatMessage(
                role="system",
                content=memory_text if memory_text else "No known user facts yet.",
            ),
            ChatMessage(role="user", content=clean_text),
        ],
    )


# -----------------------------
# Chat Endpoint
# -----------------------------


@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    user = get_default_mvp_user(db)

    clean_text = req.message.strip()

    if not clean_text:
        return ChatResponse(
            reply="Please enter a message.",
            proposed_actions=[],
        )

    # 1. Direct memory save
    if is_memory_save_request(clean_text):
        memory_content = extract_memory_content(clean_text)

        if not memory_content:
            return ChatResponse(
                reply="Tell me what you want me to remember.",
                proposed_actions=[],
            )

        duplicate = find_duplicate_memory(
            db=db,
            user_id=user.id,
            tag="user",
            content=memory_content,
        )

        if duplicate:
            return ChatResponse(
                reply=f"I already had that in memory: {duplicate.content}",
                proposed_actions=[],
            )

        memory = create_memory(
            db=db,
            user_id=user.id,
            tag="user",
            content=memory_content,
            score=max(2, memory_importance_score(memory_content)),
        )

        return ChatResponse(
            reply=f"Got it. I'll remember that: {memory.content}",
            proposed_actions=[],
        )

    # 1b. Automatic memory detection
    if (
        not clean_text.endswith("?")
        and not normalize_text(clean_text).startswith(QUESTION_STARTERS)
        and (
            should_auto_remember(clean_text)
            or memory_importance_score(clean_text) >= 2
        )
    ):
        duplicate = find_duplicate_memory(
            db=db,
            user_id=user.id,
            tag="user",
            content=clean_text,
        )

        if duplicate:
            return ChatResponse(
                reply=f"I already had that in memory: {duplicate.content}",
                proposed_actions=[],
            )

        memory = create_memory(
            db=db,
            user_id=user.id,
            tag="user",
            content=clean_text,
            score=memory_importance_score(clean_text),
        )

        return ChatResponse(
            reply=f"Got it. I'll keep that in mind: {memory.content}",
            proposed_actions=[],
        )

    # 2. Memory lookup
    memory_match = find_memory_match(db, user.id, clean_text)

    if memory_match:
        return ChatResponse(
            reply=f"You told me: {memory_match.content}",
            proposed_actions=[],
        )

    # 3. Rule-based actions
    actions = propose_actions(clean_text)

    if actions:
        top_action = actions[0]
        action_type = top_action.get("type", "action")

        if action_type == "system_info":
            info_type = top_action.get("info")
            value = top_action.get("value")

            if info_type == "time":
                reply = f"It is {value}."

            elif info_type == "date":
                reply = f"Today is {value}."

            else:
                reply = str(value)

        elif action_type == "open_app":
            app_name = top_action.get("app", "that app")
            reply = f"I can open {app_name}."

        else:
            reply = "I can perform that action."

        return ChatResponse(
            reply=reply,
            proposed_actions=actions,
        )

    # 4. Brain fallback
    brain_input = build_brain_input(db, user, req, clean_text)

    out = run_brain(
        brain_input,
        db=db,
        user_id=user.id,
    )

    return ChatResponse(
        reply=out.reply,
        proposed_actions=out.proposed_actions,
    )


# -----------------------------
# Memory Inspector Endpoint
# -----------------------------


@router.get("/memory")
def list_memory(db: Session = Depends(get_db)):
    user = get_default_mvp_user(db)

    memories = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user.id)
        .order_by(MemoryItem.id.desc())
        .all()
    )

    return [{"id": m.id, "content": m.content, "score": m.score} for m in memories]