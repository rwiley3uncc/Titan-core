"""Titan-core compatibility wrapper for Titan-AI brain orchestration.

Titan-core remains the controller layer for API/UI flows and database-backed
memory retrieval. Titan-AI now owns the actual AI orchestration path.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from sqlalchemy.orm import Session

from .memory import get_recent_memories
from .policy import apply_policy
from .rules import propose_from_text
from .schemas import BrainInput, BrainOutput, ProposedAction
from .titan_ai_imports import enable_titan_ai_imports
from .validator import validate_output

enable_titan_ai_imports()

from titan_ai.ai_types import AIMessage, AIRequest
from titan_ai.brain_router import generate_assistant_response


# Kept for backward compatibility with existing configuration. Titan-AI now
# owns the actual orchestration and model interaction path.
DEFAULT_MODEL = os.getenv("TITAN_OPENAI_MODEL", "gpt-4.1-mini")
MAX_MEMORY_ITEMS = 10


def _convert_actions(actions: list[dict]) -> list[ProposedAction]:
    out: list[ProposedAction] = []

    for action in actions:
        a_type = action.get("type")
        a_app = action.get("app")
        a_label = action.get("label")
        a_args = action.get("args", {})

        if isinstance(a_type, str):
            out.append(
                ProposedAction(
                    type=a_type.strip(),
                    app=a_app.strip() if isinstance(a_app, str) else None,
                    label=a_label.strip() if isinstance(a_label, str) else None,
                    args=a_args if isinstance(a_args, dict) else {},
                )
            )

    return out


def _to_ai_request(inp: BrainInput) -> AIRequest:
    return AIRequest(
        user_id=inp.user_id,
        role=inp.role,
        mode=inp.mode,
        tools=inp.tools,
        messages=[AIMessage(role=message.role, content=message.content) for message in inp.messages],
        context={},
    )


def _to_brain_output(output: Any) -> BrainOutput:
    return BrainOutput(
        reply=getattr(output, "reply", ""),
        proposed_actions=list(getattr(output, "proposed_actions", [])),
    )


def _latest_user_text(inp: BrainInput) -> str:
    for message in reversed(inp.messages):
        if message.role == "user":
            text = (message.content or "").strip()
            if text:
                return text
    return ""


def run_brain(
    inp: BrainInput,
    db: Optional[Session] = None,
    user_id: Optional[int] = None,
) -> BrainOutput:
    memories: list[Any] = []

    if inp.mode != "development_assistant" and db is not None and user_id is not None:
        try:
            memories = get_recent_memories(db, user_id, limit=MAX_MEMORY_ITEMS)
        except Exception:
            memories = []

    user_text = _latest_user_text(inp)
    fallback_reply, raw_actions = propose_from_text(user_text)
    ai_output = generate_assistant_response(
        _to_ai_request(inp),
        memories=memories,
        fallback_reply=fallback_reply,
        raw_actions=raw_actions,
        convert_actions=_convert_actions,
        apply_policy=apply_policy,
        validate_output=validate_output,
    )
    return _to_brain_output(ai_output)
