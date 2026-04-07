"""
Titan Core - Chat API
---------------------

Purpose:
    Handles chat requests for Titan.

Design goals:
    - Keep the route simple and predictable
    - Store direct personal facts reliably
    - Recall related facts better than raw token overlap
    - Prefer rule actions before AI fallback when appropriate
    - Keep fallback AI context small and useful
"""

from __future__ import annotations

import re
from typing import Iterable

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from titan_core.brain import run_brain
from titan_core.db import get_db
from titan_core.models import MemoryItem, User
from titan_core.rules import propose_actions
from titan_core.schemas import BrainInput, ChatMessage, ChatRequest, ChatResponse

router = APIRouter()


MEMORY_SAVE_TRIGGERS = (
    "remember that",
    "remember this",
    "titan remember",
    "hey titan remember",
    "save this",
    "store this",
    "remember",
)

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

AUTO_MEMORY_PREFIXES = (
    "i am ",
    "i'm ",
    "i was ",
    "i work ",
    "i live ",
    "i usually ",
    "i like ",
    "i love ",
    "i hate ",
    "my wife ",
    "my husband ",
    "my daughter ",
    "my son ",
    "my dog ",
    "my cat ",
    "my favorite ",
)

BRANCH_TERMS = {
    "army",
    "navy",
    "air force",
    "marines",
    "marine corps",
    "coast guard",
    "space force",
}

SYNONYM_GROUPS = (
    {"branch", "military", "service", "army", "navy", "marines", "marine", "air", "force", "coast", "guard", "space"},
    {"wife", "spouse"},
    {"husband", "spouse"},
    {"son", "child", "kid"},
    {"daughter", "child", "kid"},
    {"dog", "pet"},
    {"cat", "pet"},
    {"job", "work", "career"},
    {"home", "house", "live"},
    {"favorite", "prefer", "best"},
)


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def tokenize(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", normalize_text(text)) if len(w) > 1}


def expand_tokens(tokens: Iterable[str]) -> set[str]:
    expanded = set(tokens)
    for group in SYNONYM_GROUPS:
        if expanded & group:
            expanded |= group
    return expanded


def is_question(text: str) -> bool:
    lowered = normalize_text(text)
    return lowered.endswith("?") or lowered.startswith(QUESTION_STARTERS)


def is_memory_save_request(text: str) -> bool:
    lowered = normalize_text(text)
    return any(trigger in lowered for trigger in MEMORY_SAVE_TRIGGERS)


def should_auto_remember(text: str) -> bool:
    lowered = normalize_text(text)
    if not lowered or is_question(lowered):
        return False
    return any(lowered.startswith(prefix) for prefix in AUTO_MEMORY_PREFIXES)


def memory_importance_score(text: str) -> int:
    lowered = normalize_text(text)
    if not lowered:
        return 0

    score = 0

    if lowered.startswith(("i ", "i'm ", "i am ", "my ", "we ", "our ")):
        score += 1

    useful_keywords = (
        "work",
        "live",
        "favorite",
        "wife",
        "husband",
        "daughter",
        "son",
        "dog",
        "cat",
        "army",
        "navy",
        "marines",
        "air force",
        "coast guard",
        "space force",
        "school",
        "class",
        "usually",
        "always",
        "never",
    )
    if any(word in lowered for word in useful_keywords):
        score += 1

    if len(lowered.split()) >= 4:
        score += 1

    if is_question(lowered):
        score -= 2

    if lowered.startswith(("open ", "launch ", "start ", "create ", "draft ", "help ")):
        score -= 2

    return max(score, 0)


def extract_memory_content(text: str) -> str:
    cleaned = text.strip()
    patterns = (
        r"(?i)^hey titan remember that\s*",
        r"(?i)^titan remember that\s*",
        r"(?i)^remember that\s*",
        r"(?i)^hey titan remember\s*",
        r"(?i)^titan remember\s*",
        r"(?i)^remember this\s*",
        r"(?i)^save this\s*",
        r"(?i)^store this\s*",
        r"(?i)^remember\s*",
    )
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


def all_memories(db: Session, user_id: int) -> list[MemoryItem]:
    return (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user_id)
        .order_by(MemoryItem.id.desc())
        .all()
    )


def memory_match_score(query: str, memory_text: str) -> int:
    query_text = normalize_text(query)
    memory_norm = normalize_text(memory_text)

    query_tokens = expand_tokens(tokenize(query_text))
    memory_tokens = expand_tokens(tokenize(memory_norm))

    score = 0

    overlap = len(query_tokens & memory_tokens)
    score += overlap * 3

    if "branch" in query_tokens and any(term in memory_norm for term in BRANCH_TERMS):
        score += 6

    if "favorite" in query_tokens and "favorite" in memory_norm:
        score += 4

    if "work" in query_tokens and any(word in memory_norm for word in ("work", "job", "career")):
        score += 4

    if "live" in query_tokens and any(word in memory_norm for word in ("live", "home", "house")):
        score += 4

    if query_text in memory_norm:
        score += 5

    return score


def find_memory_match(db: Session, user_id: int, text: str) -> MemoryItem | None:
    rows = all_memories(db, user_id)
    best_row = None
    best_score = 0

    for row in rows:
        score = memory_match_score(text, row.content)
        if score > best_score:
            best_row = row
            best_score = score

    return best_row if best_score >= 4 else None


def answer_from_memory(question: str, memory: MemoryItem) -> str:
    q = normalize_text(question)
    m = memory.content.strip()

    if "branch" in q and any(term in normalize_text(m) for term in BRANCH_TERMS):
        return f"You told me you were in {m.split(' in ', 1)[-1] if ' in ' in normalize_text(m) else m}."

    if q.startswith(("what is my favorite", "what's my favorite", "favorite")):
        return f"You told me: {m}"

    if q.startswith(("where do i live", "where am i living", "where is my home")):
        return f"You told me: {m}"

    if q.startswith(("where do i work", "what is my job", "where is my job")):
        return f"You told me: {m}"

    return f"You told me: {m}"


def recent_memory_context(db: Session, user_id: int, limit: int = 8) -> str:
    rows = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user_id)
        .order_by(MemoryItem.score.desc(), MemoryItem.id.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return "No known user facts yet."

    lines = ["Known facts about the user:"]
    for row in rows:
        lines.append(f"- {row.content}")
    return "\n".join(lines)


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

    return BrainInput(
        user_id=user.id,
        role=user.role,
        mode=safe_mode,
        tools=[],
        messages=[
            ChatMessage(role="system", content=recent_memory_context(db, user.id)),
            ChatMessage(role="user", content=clean_text),
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
        return ChatResponse(reply="Please enter a message.", proposed_actions=[])

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

    if should_auto_remember(clean_text) or memory_importance_score(clean_text) >= 2:
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

    memory_match = find_memory_match(db, user.id, clean_text)
    if memory_match:
        return ChatResponse(
            reply=answer_from_memory(clean_text, memory_match),
            proposed_actions=[],
        )

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

        return ChatResponse(reply=reply, proposed_actions=actions)

    brain_input = build_brain_input(db, user, req, clean_text)
    out = run_brain(brain_input, db=db, user_id=user.id)
    return ChatResponse(reply=out.reply, proposed_actions=out.proposed_actions)


@router.get("/memory")
def list_memory(db: Session = Depends(get_db)):
    user = get_default_mvp_user(db)
    memories = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user.id)
        .order_by(MemoryItem.score.desc(), MemoryItem.id.desc())
        .all()
    )
    return [
        {"id": m.id, "content": m.content, "score": m.score}
        for m in memories
    ]