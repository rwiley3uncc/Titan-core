"""
Titan Core - Rule-Based Planning Engine
----------------------------------------

Purpose:
    Lightweight deterministic rules engine used by the Brain
    during MVP phase.

Role in Architecture:
    Brain -> Rules -> (reply, raw action dicts)

    This module:
        - Does NOT execute tools
        - Does NOT access database
        - Only proposes structured action dictionaries

Design Notes:
    - Deterministic (no randomness)
    - Side-effect free
    - Easily replaceable with LLM planner
    - Order of rules is intentional

Author:
    Ron Wiley
Project:
    Titan AI - Operational Personnel Assistant
"""

import re
from datetime import datetime, timedelta
from typing import Tuple, List, Dict, Any


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _iso(dt: datetime) -> str:
    """Convert datetime to ISO-8601 string."""
    return dt.isoformat()


# ---------------------------------------------------------------------
# Core Rule Engine
# ---------------------------------------------------------------------

def propose_from_text(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Analyze raw user text and propose actions.

    Rules:
        - "draft email"      -> draft_email
        - "remember ..."     -> save_memory
        - "remind me"        -> create_task
        - default fallback   -> tutoring helper

    Returns:
        (reply: str, actions: list[dict])
    """

    if not text or not text.strip():
        return "No input detected.", []

    original_text = text.strip()
    t = original_text.lower()

    actions: List[Dict[str, Any]] = []

    # -----------------------------------------------------------------
    # Email Drafting Rule
    # -----------------------------------------------------------------

    if "draft email" in t or "email to" in t:
        actions.append({
            "type": "draft_email",
            "args": {
                "content": "DRAFT (placeholder):\n\nHello,\n\n..."
            }
        })

        return (
            "I can draft that email. Would you like it formal, professional, or casual?",
            actions
        )

    # -----------------------------------------------------------------
    # Memory Save Rule
    # -----------------------------------------------------------------

    if "remember that" in t or t.startswith("remember "):
        content = re.sub(
            r"^remember( that)?\s*",
            "",
            original_text,
            flags=re.I
        )

        actions.append({
            "type": "save_memory",
            "args": {
                "tag": "user",
                "content": content,
                "score_delta": 1
            }
        })

        return (
            "I can save that as a memory item. Approve when ready.",
            actions
        )

    # -----------------------------------------------------------------
    # Task / Reminder Rule
    # -----------------------------------------------------------------

    if (
        "remind me" in t
        or "set a reminder" in t
        or "make a task" in t
        or t.startswith("task ")
    ):
        due_at = None

        # Simple heuristic for MVP
        if "tomorrow" in t:
            due = datetime.now() + timedelta(days=1)
            due = due.replace(hour=18, minute=0, second=0, microsecond=0)
            due_at = _iso(due)

        actions.append({
            "type": "create_task",
            "args": {
                "title": original_text,
                "due_at": due_at
            }
        })

        return (
            "I can create a task for that. Review and approve it.",
            actions
        )

    # -----------------------------------------------------------------
    # Default Fallback (Tutor Mode)
    # -----------------------------------------------------------------

    return (
        "Tell me the class or topic and what you need: explanation, study plan, or checklist.",
        []
    )