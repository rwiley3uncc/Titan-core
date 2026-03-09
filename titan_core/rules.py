"""
Titan Core - Rules Engine
-------------------------

Purpose:
    Deterministic lightweight action proposal layer.

Role in Architecture:
    API / Brain fallback -> Rules -> Proposed Actions

Design Rules:
    - No execution
    - No DB writes
    - Only propose actions
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------
# App aliases
# ---------------------------------------------------------------------

APP_ALIASES: dict[str, list[str]] = {
    "vscode": [
        "vscode",
        "vs code",
        "visual studio code",
        "code",
    ],
    "chrome": [
        "chrome",
        "google chrome",
    ],
    "edge": [
        "edge",
        "microsoft edge",
    ],
    "firefox": [
        "firefox",
        "mozilla firefox",
    ],
    "powershell": [
        "powershell",
        "power shell",
    ],
    "cmd": [
        "cmd",
        "command prompt",
        "terminal",
    ],
    "explorer": [
        "explorer",
        "file explorer",
    ],
    "notepad": [
        "notepad",
    ],
    "calculator": [
        "calculator",
        "calc",
    ],
    "discord": [
        "discord",
    ],
    "spotify": [
        "spotify",
    ],
    "settings": [
        "settings",
        "windows settings",
    ],
}

OPEN_VERBS = {
    "open",
    "launch",
    "start",
    "run",
    "load",
    "bring up",
}


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def contains_open_verb(text: str) -> bool:
    normalized = normalize_text(text)
    return any(verb in normalized for verb in OPEN_VERBS)


def find_app_name(text: str) -> str | None:
    normalized = normalize_text(text)

    for app_key, aliases in APP_ALIASES.items():
        for alias in aliases:
            alias_norm = normalize_text(alias)

            if normalized == alias_norm:
                return app_key

            if alias_norm in normalized:
                return app_key

    return None


def contains_any(text: str, phrases: list[str]) -> bool:
    normalized = normalize_text(text)
    return any(phrase in normalized for phrase in phrases)


def extract_after_prefix(text: str, prefixes: list[str]) -> str:
    stripped = text.strip()
    lowered = stripped.lower()

    for prefix in prefixes:
        if lowered.startswith(prefix):
            return stripped[len(prefix):].strip()

    return stripped


# ---------------------------------------------------------------------
# Rule functions
# ---------------------------------------------------------------------

def rule_open_app(user_text: str) -> dict[str, Any] | None:
    normalized = normalize_text(user_text)

    app_name = find_app_name(normalized)
    if not app_name:
        return None

    if contains_open_verb(normalized):
        return {
            "type": "open_app",
            "app": app_name,
            "confidence": 0.98,
            "source": "rules",
            "reason": f"Detected app launch request for '{app_name}'.",
            "text": user_text,
        }

    if normalized == app_name or normalized in [normalize_text(a) for a in APP_ALIASES[app_name]]:
        return {
            "type": "open_app",
            "app": app_name,
            "confidence": 0.72,
            "source": "rules",
            "reason": f"Detected likely standalone app request for '{app_name}'.",
            "text": user_text,
        }

    return None


def rule_create_task(user_text: str) -> dict[str, Any] | None:
    text = normalize_text(user_text)

    task_prefixes = [
        "remind me to ",
        "create a task to ",
        "make a task to ",
        "add a task to ",
        "todo ",
        "to do ",
    ]

    for prefix in task_prefixes:
        if text.startswith(prefix):
            title = extract_after_prefix(user_text, [prefix]).strip()

            if not title:
                return None

            return {
                "type": "create_task",
                "args": {
                    "title": title,
                    "due_at": None,
                },
                "confidence": 0.95,
                "source": "rules",
                "reason": f"Detected task creation request for '{title}'.",
                "text": user_text,
            }

    return None


def rule_draft_email(user_text: str) -> dict[str, Any] | None:
    text = normalize_text(user_text)

    email_prefixes = [
        "draft an email to ",
        "write an email to ",
        "compose an email to ",
        "draft email to ",
    ]

    for prefix in email_prefixes:
        if text.startswith(prefix):
            target = extract_after_prefix(user_text, [prefix]).strip()

            return {
                "type": "draft_email",
                "args": {
                    "target": target if target else "recipient",
                    "prompt": user_text.strip(),
                },
                "confidence": 0.94,
                "source": "rules",
                "reason": "Detected email drafting request.",
                "text": user_text,
            }

    return None


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def propose_actions(user_text: str) -> list[dict[str, Any]]:
    proposals: list[dict[str, Any]] = []

    if not normalize_text(user_text):
        return proposals

    open_app_action = rule_open_app(user_text)
    if open_app_action:
        proposals.append(open_app_action)

    create_task_action = rule_create_task(user_text)
    if create_task_action:
        proposals.append(create_task_action)

    draft_email_action = rule_draft_email(user_text)
    if draft_email_action:
        proposals.append(draft_email_action)

    proposals.sort(key=lambda item: item.get("confidence", 0), reverse=True)
    return proposals


def propose_from_text(user_text: str) -> tuple[str, list[dict[str, Any]]]:
    text = normalize_text(user_text)
    actions = propose_actions(user_text)

    if not text:
        return "Please enter a message.", actions

    if actions:
        top_action = actions[0]
        action_type = top_action.get("type")

        if action_type == "open_app":
            app_name = top_action.get("app", "that app")
            return f"I can open {app_name}.", actions

        if action_type == "create_task":
            title = top_action.get("args", {}).get("title", "that task")
            return f'I can create a task for "{title}". Approve when ready.', actions

        if action_type == "draft_email":
            return "I can draft that email for review. Approve when ready.", actions

    if text in {"hi", "hello", "hey", "yo"}:
        return "Hey. What can I help you with?", actions

    if contains_any(text, ["remember that", "remember this", "titan remember"]):
        return "Got it.", actions

    planning_terms = [
        "plan",
        "organize",
        "schedule",
        "roadmap",
        "strategy",
        "next steps",
        "figure this out",
    ]

    if contains_any(text, planning_terms):
        return "I can help break that down into clear steps. Tell me the goal.", actions

    return (
        "How can I help?\n"
        "• open an app\n"
        "• remember something\n"
        "• create a task\n"
        "• draft something\n"
        "• help plan something",
        actions,
    )