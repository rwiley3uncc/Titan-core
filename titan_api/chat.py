"""
Titan Core - Chat API
---------------------

Purpose:
    Handles chat requests for Titan.

Flow:
    1. Accept chat request
    2. Resolve temporary MVP user
    3. Save explicit memory requests directly
    4. Search memory before AI fallback
    5. Check rule-based actions before brain fallback
    6. Return reply and any proposed actions
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from titan_core.db import get_db
from titan_core.models import User, MemoryItem
from titan_core.schemas import BrainInput, ChatRequest, ChatResponse, ChatMessage
from titan_core.brain import run_brain
from titan_core.tools.rules import propose_actions

router = APIRouter()


MEMORY_SAVE_TRIGGERS = [
    "remember that",
    "remember this",
    "titan remember",
    "hey titan remember",
    "save this",
    "store this",
]


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def tokenize(text: str) -> set[str]:
    words = re.findall(r"\w+", normalize_text(text))
    return {word for word in words if len(word) > 2}


def is_memory_save_request(text: str) -> bool:
    lowered = normalize_text(text)
    return any(trigger in lowered for trigger in MEMORY_SAVE_TRIGGERS)


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


def get_default_mvp_user(db: Session) -> User:
    user = db.query(User).filter(User.username == "ron").first()
    if not user:
        raise RuntimeError("Default user not found. Run /seed first.")
    return user


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


def build_brain_input(user: User, req: ChatRequest, clean_text: str) -> BrainInput:
    """
    Build BrainInput for fallback AI handling.
    """

    allowed_modes = {
        "personal_general",
        "personal_productivity",
        "personal_builder",
        "personal_family",
    }

    safe_mode = req.mode if req.mode in allowed_modes else "personal_general"

    return BrainInput(
        user_id=user.id,
        role=user.role,
        mode=safe_mode,
        tools=[],
        messages=[
            ChatMessage(role="user", content=clean_text)
        ],
    )
@router.post("/chat", response_model=ChatResponse)
def chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    user = get_default_mvp_user(db)

    clean_text = req.message.strip()
    if not clean_text:
       print("ACTIONS RETURNED:", actions)
       
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
            score=1,
        )

        return ChatResponse(
            reply=f"Got it. I'll remember that: {memory.content}",
            proposed_actions=[],
        )

    # 2. Memory lookup
    memory_match = find_memory_match(db, user.id, clean_text)
    if memory_match:
        return ChatResponse(
            reply=f"You told me: {memory_match.content}",
            proposed_actions=[],
        )

    # 3. Rule-based actions before brain
    actions = propose_actions(clean_text)
    if actions:
        top_action = actions[0]
        action_type = top_action.get("type", "action")

        if action_type == "open_app":
            app_name = top_action.get("app", "that app")
            reply = f"I can open {app_name}."
        else:
            reply = "I can perform that action."

        print("ACTIONS RETURNED:", actions)

        return ChatResponse(
            reply=reply,
            proposed_actions=actions,
        )

    # 4. Brain fallback
    brain_input = build_brain_input(user, req, clean_text)

    out = run_brain(
        brain_input,
        db=db,
        user_id=user.id,
    )

    return ChatResponse(
        reply=out.reply,
        proposed_actions=out.proposed_actions,
    )