"""
controller.py

Purpose:
Main request handler for Titan.

Flow:
1. Receive user text
2. Check for rule-based actions
3. Execute the best action if allowed
4. Return a response payload to the UI
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.rules import propose_actions, best_action
from tools.executor import execute_action


def build_chat_response(
    user_text: str,
    message: str,
    actions: Optional[List[Dict[str, Any]]] = None,
    executed: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Standard response payload back to the UI.
    """
    return {
        "ok": True,
        "user_text": user_text,
        "message": message,
        "actions": actions or [],
        "executed": executed,
    }


def handle_action(user_text: str) -> Dict[str, Any]:
    """
    Run rules against the user text and execute the best action if found.
    """
    actions = propose_actions(user_text)

    if not actions:
        return build_chat_response(
            user_text=user_text,
            message=f'I heard: "{user_text}"',
            actions=[],
            executed=None,
        )

    action = best_action(user_text)
    if not action:
        return build_chat_response(
            user_text=user_text,
            message="I found possible actions, but none were strong enough to run.",
            actions=actions,
            executed=None,
        )

    result = execute_action(action)

    if result.get("status") == "ok":
        app_name = action.get("app", "that app")
        return build_chat_response(
            user_text=user_text,
            message=f"Opening {app_name}.",
            actions=actions,
            executed={
                "action": action,
                "result": result,
            },
        )

    if result.get("status") == "error":
        return build_chat_response(
            user_text=user_text,
            message=result.get("message", "I tried to run that action, but it failed."),
            actions=actions,
            executed={
                "action": action,
                "result": result,
            },
        )

    return build_chat_response(
        user_text=user_text,
        message="I understood the request, but nothing was executed.",
        actions=actions,
        executed={
            "action": action,
            "result": result,
        },
    )


def process_input(user_text: str) -> Dict[str, Any]:
    """
    Main entry point for Titan.
    Call this from your API route or UI handler.
    """
    if not user_text or not user_text.strip():
        return build_chat_response(
            user_text=user_text,
            message="Please type a command.",
            actions=[],
            executed=None,
        )

    return handle_action(user_text.strip())


# Optional aliases in case another file imports different names
handle_user_input = process_input
run_controller = process_input


if __name__ == "__main__":
    tests = [
        "open vscode",
        "launch chrome",
        "start powershell",
        "open notepad",
        "hello titan",
    ]

    for text in tests:
        print("\nINPUT:", text)
        print(process_input(text))