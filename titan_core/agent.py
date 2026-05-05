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
    confidence: float = 0.0
    reason: str = ""
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


def _matches_any(normalized: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in normalized for phrase in phrases)


def _build_agent_action(
    *,
    name: str,
    description: str,
    payload: dict[str, Any],
    confidence: float,
    reason: str,
) -> AgentAction | None:
    if confidence < 0.5:
        return None
    return AgentAction(
        name=name,
        description=description,
        confidence=confidence,
        reason=reason,
        payload=payload,
    )


def plan_agent_action(user_message: str) -> AgentAction | None:
    """
    First-pass keyword planner for safe action proposals only.

    This planner does not execute commands, open apps, fetch network data,
    or modify the system. It only returns a proposed action object when the
    request matches a small safe allow-list.
    """
    normalized = _normalize_text(user_message)
    exact_vscode = ("open vscode", "launch vscode", "start vscode", "open vs code", "open visual studio code")
    partial_vscode = ("can you open vscode", "could you open vscode", "please open vscode", "open vscode for me")
    weak_vscode = ("maybe open something like vscode", "something like vscode", "vscode")
    exact_edge = ("open edge", "launch edge", "start edge", "open microsoft edge")
    partial_edge = ("can you open edge", "could you open edge", "please open edge", "open edge for me")
    weak_edge = ("maybe open something like edge", "something like edge", "edge")
    exact_refresh = ("refresh my sitrep", "refresh sitrep", "reload sitrep", "update sitrep")
    partial_refresh = ("can you refresh my sitrep", "please refresh my sitrep", "refresh the sitrep")
    weak_refresh = ("maybe refresh sitrep", "sitrep refresh", "sitrep")
    exact_read = ("read my sitrep", "read sitrep", "speak sitrep", "say my sitrep")
    partial_read = ("can you read my sitrep", "please read my sitrep", "read the sitrep aloud")
    weak_read = ("maybe read sitrep", "sitrep aloud", "speak my sitrep")

    if _matches_any(normalized, exact_refresh):
        return _build_agent_action(
            name="refresh_sitrep",
            description="Refresh sitrep",
            payload={},
            confidence=0.95,
            reason="User directly requested to refresh the sitrep.",
        )
    if _matches_any(normalized, partial_refresh):
        return _build_agent_action(
            name="refresh_sitrep",
            description="Refresh sitrep",
            payload={},
            confidence=0.85,
            reason="User intent strongly suggests refreshing the sitrep.",
        )
    if _matches_any(normalized, weak_refresh):
        return _build_agent_action(
            name="refresh_sitrep",
            description="Refresh sitrep",
            payload={},
            confidence=0.6,
            reason="User mentioned the sitrep, but the refresh request is somewhat indirect.",
        )

    if _matches_any(normalized, exact_read):
        return _build_agent_action(
            name="read_sitrep",
            description="Read current sitrep aloud",
            payload={},
            confidence=0.95,
            reason="User directly requested to read the sitrep aloud.",
        )
    if _matches_any(normalized, partial_read):
        return _build_agent_action(
            name="read_sitrep",
            description="Read current sitrep aloud",
            payload={},
            confidence=0.85,
            reason="User intent strongly suggests reading the sitrep aloud.",
        )
    if _matches_any(normalized, weak_read):
        return _build_agent_action(
            name="read_sitrep",
            description="Read current sitrep aloud",
            payload={},
            confidence=0.6,
            reason="User mentioned having the sitrep read aloud, but intent is somewhat uncertain.",
        )

    if _matches_any(normalized, exact_vscode):
        return _build_agent_action(
            name="open_vscode",
            description="Open VS Code",
            payload={"app": "vscode"},
            confidence=0.95,
            reason="User directly requested to open VS Code.",
        )
    if _matches_any(normalized, partial_vscode):
        return _build_agent_action(
            name="open_vscode",
            description="Open VS Code",
            payload={"app": "vscode"},
            confidence=0.85,
            reason="User intent strongly suggests opening VS Code.",
        )
    if _matches_any(normalized, weak_vscode):
        return _build_agent_action(
            name="open_vscode",
            description="Open VS Code",
            payload={"app": "vscode"},
            confidence=0.6,
            reason="User mentioned VS Code but intent is uncertain.",
        )

    if _matches_any(normalized, exact_edge):
        return _build_agent_action(
            name="open_edge",
            description="Open Microsoft Edge",
            payload={"app": "edge"},
            confidence=0.95,
            reason="User directly requested to open Microsoft Edge.",
        )
    if _matches_any(normalized, partial_edge):
        return _build_agent_action(
            name="open_edge",
            description="Open Microsoft Edge",
            payload={"app": "edge"},
            confidence=0.85,
            reason="User intent strongly suggests opening Microsoft Edge.",
        )
    if _matches_any(normalized, weak_edge):
        return _build_agent_action(
            name="open_edge",
            description="Open Microsoft Edge",
            payload={"app": "edge"},
            confidence=0.6,
            reason="User mentioned Edge but intent is uncertain.",
        )

    return None


def validate_agent_action(action: AgentAction | None) -> bool:
    """
    Allow only explicitly safe, allow-listed action names.

    This validation is intentionally narrow for the first agent pass.
    """
    return bool(action and action.name in SAFE_ACTIONS)
