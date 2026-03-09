"""
rules.py

Purpose:
Simple rule-based intent parsing for Titan.

This file looks at a user's message and proposes actions that Titan
could take. Right now it focuses on app launching so Titan can suggest
an `open_app` action for commands like:

- "open vscode"
- "launch chrome"
- "start powershell"

You can expand APP_ALIASES later with more apps and more phrasing.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------
# App aliases
# ---------------------------------------------------------------------
# Key = Titan's internal app name
# Values = phrases the user might type
APP_ALIASES: Dict[str, List[str]] = {
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
        "file explorer",
        "explorer",
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

# Words that suggest opening/starting an app
OPEN_VERBS = {
    "open",
    "launch",
    "start",
    "run",
    "load",
    "bring up",
}
# ---------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """
    Lowercase and collapse extra whitespace.
    """
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def find_app_name(text: str) -> Optional[str]:
    """
    Try to map user text to one of the known app keys in APP_ALIASES.
    Returns the internal app key if matched, otherwise None.
    """
    normalized = normalize_text(text)

    for app_key, aliases in APP_ALIASES.items():
        for alias in aliases:
            alias_norm = normalize_text(alias)

            # Exact match
            if normalized == alias_norm:
                return app_key

            # Phrase contained in command
            if alias_norm in normalized:
                return app_key

    return None


def contains_open_verb(text: str) -> bool:
    """
    Check whether the text includes a launch/open style verb.
    """
    normalized = normalize_text(text)
    return any(verb in normalized for verb in OPEN_VERBS)


# ---------------------------------------------------------------------
# Rule functions
# ---------------------------------------------------------------------


def rule_open_app(text: str) -> Optional[Dict[str, Any]]:
    """
    Propose an open_app action if the message looks like an app launch request.
    Examples:
        "open vscode"
        "launch chrome"
        "start powershell"
    """
    normalized = normalize_text(text)

    app_name = find_app_name(normalized)
    if not app_name:
        return None

    # Strong match: explicit open verb + known app
    if contains_open_verb(normalized):
        return {
            "type": "open_app",
            "app": app_name,
            "confidence": 0.98,
            "source": "rules",
            "reason": f"Detected app launch request for '{app_name}'.",
            "text": text,
        }

    # Medium match: user typed just the app name, like "vscode"
    if normalized == app_name or normalized in [normalize_text(a) for a in APP_ALIASES[app_name]]:
        return {
            "type": "open_app",
            "app": app_name,
            "confidence": 0.72,
            "source": "rules",
            "reason": f"Detected likely standalone app request for '{app_name}'.",
            "text": text,
        }

    return None


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------


def propose_actions(text: str) -> List[Dict[str, Any]]:
    """
    Main entry point.

    Returns a list of proposed actions based on the input text.
    Higher-confidence rules should appear first.
    """
    proposals: List[Dict[str, Any]] = []

    open_app_action = rule_open_app(text)
    if open_app_action:
        proposals.append(open_app_action)

    proposals.sort(key=lambda item: item.get("confidence", 0), reverse=True)
    return proposals


def best_action(text: str) -> Optional[Dict[str, Any]]:
    """
    Convenience helper: return the single best action or None.
    """
    proposals = propose_actions(text)
    return proposals[0] if proposals else None


# ---------------------------------------------------------------------
# Quick manual test
# ---------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        "open vscode",
        "launch chrome",
        "start powershell",
        "open visual studio code",
        "vscode",
        "calculator",
        "what is the weather",
    ]

    for test in tests:
        print(f"\nINPUT: {test}")
        print(propose_actions(test))