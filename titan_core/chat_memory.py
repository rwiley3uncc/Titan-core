from __future__ import annotations

import re

from sqlalchemy.orm import Session

from titan_core.config import settings
from titan_core.models import MemoryItem, User

from .chat_mode import is_question, normalize_text, tokenize


MEMORY_SAVE_TRIGGERS = ("remember that", "remember this", "titan remember", "hey titan remember", "save this", "store this", "remember")
AUTO_MEMORY_PREFIXES = ("i am ", "i'm ", "i was ", "i work ", "i live ", "i usually ", "i like ", "i love ", "i hate ", "my wife ", "my husband ", "my daughter ", "my son ", "my dog ", "my cat ", "my favorite ")
BRANCH_TERMS = {"army", "navy", "air force", "marines", "marine corps", "coast guard", "space force"}
SYNONYM_GROUPS = (
    {"branch", "military", "service", "army", "navy", "marines", "marine", "air", "force", "coast", "guard", "space"},
    {"wife", "spouse"}, {"husband", "spouse"}, {"son", "child", "kid"}, {"daughter", "child", "kid"}, {"dog", "pet"}, {"cat", "pet"}, {"job", "work", "career"}, {"home", "house", "live"}, {"favorite", "prefer", "best"},
)


def expand_tokens(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for group in SYNONYM_GROUPS:
        if expanded & group:
            expanded |= group
    return expanded


def is_memory_save_request(text: str) -> bool:
    lowered = normalize_text(text)
    return any(trigger in lowered for trigger in MEMORY_SAVE_TRIGGERS)


def should_auto_remember(text: str) -> bool:
    lowered = normalize_text(text)
    return bool(lowered) and not is_question(lowered) and any(lowered.startswith(prefix) for prefix in AUTO_MEMORY_PREFIXES)


def memory_importance_score(text: str) -> int:
    lowered = normalize_text(text)
    if not lowered:
        return 0
    score = 0
    if lowered.startswith(("i ", "i'm ", "i am ", "my ", "we ", "our ")):
        score += 1
    useful_keywords = ("work", "live", "favorite", "wife", "husband", "daughter", "son", "dog", "cat", "army", "navy", "marines", "air force", "coast guard", "space force", "school", "class", "usually", "always", "never")
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
    patterns = (r"(?i)^hey titan remember that\s*", r"(?i)^titan remember that\s*", r"(?i)^remember that\s*", r"(?i)^hey titan remember\s*", r"(?i)^titan remember\s*", r"(?i)^remember this\s*", r"(?i)^save this\s*", r"(?i)^store this\s*", r"(?i)^remember\s*")
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned).strip()
    return cleaned


def get_default_mvp_user(db: Session) -> User:
    user = db.query(User).filter(User.username == settings.owner_username).first()
    if not user:
        raise RuntimeError("Default user not found. Run /seed first.")
    return user


def find_duplicate_memory(db: Session, user_id: int, tag: str, content: str) -> MemoryItem | None:
    normalized_new = normalize_text(content)
    rows = db.query(MemoryItem).filter(MemoryItem.user_id == user_id, MemoryItem.tag == tag).order_by(MemoryItem.id.desc()).all()
    for row in rows:
        if normalize_text(row.content) == normalized_new:
            return row
    return None


def create_memory(db: Session, user_id: int, tag: str, content: str, score: int = 1) -> MemoryItem:
    memory = MemoryItem(user_id=user_id, tag=tag, content=content, score=score)
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def all_memories(db: Session, user_id: int) -> list[MemoryItem]:
    return db.query(MemoryItem).filter(MemoryItem.user_id == user_id).order_by(MemoryItem.id.desc()).all()


def memory_match_score(query: str, memory_text: str) -> int:
    query_text = normalize_text(query)
    memory_norm = normalize_text(memory_text)
    query_tokens = expand_tokens(tokenize(query_text))
    memory_tokens = expand_tokens(tokenize(memory_norm))
    score = len(query_tokens & memory_tokens) * 3
    if "branch" in query_tokens and any(term in memory_norm for term in BRANCH_TERMS):
        score += 6
    if query_text in memory_norm:
        score += 5
    return score


def find_memory_match(db: Session, user_id: int, text: str) -> MemoryItem | None:
    best_row = None
    best_score = 0
    for row in all_memories(db, user_id):
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
    return f"You told me: {m}"


def recent_memory_context(db: Session, user_id: int, limit: int = 8) -> str:
    rows = db.query(MemoryItem).filter(MemoryItem.user_id == user_id).order_by(MemoryItem.score.desc(), MemoryItem.id.desc()).limit(limit).all()
    return "No known user facts yet." if not rows else "\n".join(["Known facts about the user:"] + [f"- {row.content}" for row in rows])
