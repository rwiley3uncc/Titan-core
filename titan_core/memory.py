"""
Titan Core - Memory Engine
--------------------------

Purpose:
    Handles storage and retrieval of user memories.

Design:
    Uses MemoryItem SQLAlchemy model.
    Keeps logic separate from API layer.

Capabilities:
    - save memory
    - fetch recent memory
    - search memory
"""

from sqlalchemy.orm import Session
from titan_core.models import MemoryItem


# ------------------------------------------------------------
# Save memory
# ------------------------------------------------------------

def save_memory(db: Session, user_id: int, content: str, tag: str = "general"):
    item = MemoryItem(
        user_id=user_id,
        content=content,
        tag=tag
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return item


# ------------------------------------------------------------
# Get recent memory
# ------------------------------------------------------------

def get_recent_memories(db: Session, user_id: int, limit: int = 10):
    return (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user_id)
        .order_by(MemoryItem.created_at.desc())
        .limit(limit)
        .all()
    )


# ------------------------------------------------------------
# Search memory
# ------------------------------------------------------------

def search_memories(db: Session, user_id: int, text: str, limit: int = 5):
    return (
        db.query(MemoryItem)
        .filter(
            MemoryItem.user_id == user_id,
            MemoryItem.content.ilike(f"%{text}%")
        )
        .order_by(MemoryItem.score.desc())
        .limit(limit)
        .all()
    )