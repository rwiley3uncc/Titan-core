"""
Titan Core - Action Dispatcher / Executor
-----------------------------------------

Purpose:
    Executes validated actions proposed by the Brain.

Role in Architecture:
    Brain -> Validator -> Dispatcher -> Database

Responsibilities:
    - Persist tasks
    - Persist memory items
    - Persist drafts
    - Handle transactional integrity
    - Return structured execution results

Design Notes:
    - All database writes are atomic
    - Rolls back on failure
    - Unknown actions fail safely
    - Does NOT decide what actions to run (Brain does that)

Author:
    Ron Wiley
Project:
    Titan AI - Operational Personnel Assistant
"""

from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from .models import Task, MemoryItem, Draft


# ---------------------------------------------------------------------
# Core Execution Function
# ---------------------------------------------------------------------

def execute_action(db: Session, user_id: int, action: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes a single proposed action.

    Parameters:
        db (Session): Active database session
        user_id (int): Authenticated user ID
        action (dict): Proposed action dictionary

    Returns:
        dict: Execution result metadata
    """

    action_type = action.get("type")
    args = action.get("args", {})

    try:

        # -------------------------------------------------------------
        # CREATE TASK
        # -------------------------------------------------------------
        if action_type == "create_task":

            task = Task(
                user_id=user_id,
                title=args.get("title", "(untitled)"),
                due_at=args.get("due_at")
            )

            db.add(task)
            db.commit()
            db.refresh(task)

            return {
                "ok": True,
                "type": action_type,
                "task_id": task.id
            }

        # -------------------------------------------------------------
        # SAVE MEMORY
        # -------------------------------------------------------------
        if action_type == "save_memory":

            memory = MemoryItem(
                user_id=user_id,
                tag=args.get("tag", "general"),
                content=args.get("content", ""),
                score=int(args.get("score_delta", 0)),
            )

            db.add(memory)
            db.commit()
            db.refresh(memory)

            return {
                "ok": True,
                "type": action_type,
                "memory_id": memory.id
            }

        # -------------------------------------------------------------
        # DRAFT EMAIL
        # -------------------------------------------------------------
        if action_type == "draft_email":

            draft = Draft(
                user_id=user_id,
                kind="email",
                content=args.get("content", "")
            )

            db.add(draft)
            db.commit()
            db.refresh(draft)

            return {
                "ok": True,
                "type": action_type,
                "draft_id": draft.id
            }

        # -------------------------------------------------------------
        # UNKNOWN ACTION
        # -------------------------------------------------------------
        return {
            "ok": False,
            "type": action_type,
            "error": "Unknown action type"
        }

    except SQLAlchemyError as e:
        db.rollback()
        return {
            "ok": False,
            "type": action_type,
            "error": "Database error",
            "detail": str(e)
        }