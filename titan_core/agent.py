"""
Titan Core - Safe Agent Planning Layer
--------------------------------------

This is the first safe Titan agent layer.
It can inspect a user message and propose a small allow-listed action,
but it must not execute anything directly.

Execution must remain inside the existing approved action system, with
allow-listed action names and explicit user approval from the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import re
import time
from uuid import uuid4


@dataclass(frozen=True)
class AgentAction:
    name: str
    description: str
    action_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: float = field(default_factory=time.time)
    status: str = "pending"
    payload: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = True


SAFE_ACTIONS = {
    "refresh_sitrep",
    "read_sitrep",
    "open_vscode",
    "open_edge",
}


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def plan_agent_action(user_message: str) -> AgentAction | None:
    """
    First-pass keyword planner for safe action proposals only.

    This planner does not execute commands, open apps, fetch network data,
    or modify the system. It only returns a proposed action object when the
    request matches a small safe allow-list.
    """
    normalized = _normalize_text(user_message)

    if any(phrase in normalized for phrase in ("refresh my sitrep", "refresh sitrep", "reload sitrep", "update sitrep")):
        return AgentAction(
            name="refresh_sitrep",
            description="Refresh sitrep",
            payload={},
        )

    if any(phrase in normalized for phrase in ("read my sitrep", "read sitrep", "speak sitrep", "say my sitrep")):
        return AgentAction(
            name="read_sitrep",
            description="Read current sitrep aloud",
            payload={},
        )

    if any(phrase in normalized for phrase in ("open vscode", "launch vscode", "start vscode", "open vs code", "open visual studio code")):
        return AgentAction(
            name="open_vscode",
            description="Open VS Code",
            payload={"app": "vscode"},
        )

    if any(phrase in normalized for phrase in ("open edge", "launch edge", "start edge", "open microsoft edge")):
        return AgentAction(
            name="open_edge",
            description="Open Microsoft Edge",
            payload={"app": "edge"},
        )

    return None


def validate_agent_action(action: AgentAction | None) -> bool:
    """
    Allow only explicitly safe, allow-listed action names.

    This validation is intentionally narrow for the first agent pass.
    """
    return bool(action and action.name in SAFE_ACTIONS)
