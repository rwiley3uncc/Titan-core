"""
Titan Core - Chat Router (Controller Layer)
--------------------------------------------

Flow:
    Request -> Brain -> Validator -> Policy -> Response

MVP Notes:
    - We return proposed actions for SIM review.
    - REAL mode execution engine comes later.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter
from pydantic import BaseModel, Field

from titan_core.schemas import BrainOutput
from titan_core.validator import validate_output


router = APIRouter(tags=["chat"])


# ---------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    mode: str = Field("SIM", description="SIM returns proposed actions; REAL reserved for later.")


class PolicyResult(BaseModel):
    allowed: bool = True
    reason: str = "OK"


class ChatResponse(BaseModel):
    reply: str
    mode: str
    policy: PolicyResult
    proposed_actions: list[dict[str, Any]]


# ---------------------------------------------------------------------
# Brain adapter
# ---------------------------------------------------------------------

def _resolve_brain_callable() -> Callable[[str], BrainOutput]:
    """
    Finds an entry function in brain.py.

    Acceptable function names:
        run_brain(message) -> BrainOutput
        respond(message)   -> BrainOutput
        chat(message)      -> BrainOutput
    """
    from titan_core import brain as brain_mod

    for name in ("run_brain", "respond", "chat"):
        fn = getattr(brain_mod, name, None)
        if callable(fn):
            return fn  # type: ignore[return-value]

    raise RuntimeError(
        "No brain entry function found in titan_core/brain.py. "
        "Create one: run_brain(message: str) -> BrainOutput (or respond/chat)."
    )


def _call_brain(message: str) -> BrainOutput:
    fn = _resolve_brain_callable()
    out = fn(message)
    if not isinstance(out, BrainOutput):
        raise RuntimeError("Brain did not return BrainOutput. Check schemas.py and brain.py.")
    return out


# ---------------------------------------------------------------------
# Policy adapter
# ---------------------------------------------------------------------

def _apply_policy(out: BrainOutput) -> PolicyResult:
    """
    Calls your policy module if it exposes one of these functions:
        enforce(out) -> (bool, str) OR dict OR PolicyResult
        validate(out) -> ...
        check(out) -> ...

    If no function is found, we default to allow (MVP).
    """
    try:
        from titan_core import policy as policy_mod
    except Exception:
        return PolicyResult(allowed=True, reason="Policy module import failed (MVP allow).")

    for name in ("enforce", "validate", "check", "evaluate"):
        fn = getattr(policy_mod, name, None)
        if not callable(fn):
            continue

        result = fn(out)

        if isinstance(result, PolicyResult):
            return result
        if isinstance(result, tuple) and len(result) == 2:
            allowed, reason = result
            return PolicyResult(allowed=bool(allowed), reason=str(reason))
        if isinstance(result, dict):
            return PolicyResult(
                allowed=bool(result.get("allowed", True)),
                reason=str(result.get("reason", "OK")),
            )

        return PolicyResult(allowed=True, reason=f"Policy returned unsupported type: {type(result).__name__} (MVP allow).")

    return PolicyResult(allowed=True, reason="No policy function found (MVP allow).")


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _actions_to_dicts(out: BrainOutput) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for a in out.proposed_actions:
        actions.append({"type": a.type, "args": a.args})
    return actions


# ---------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------

@router.get("/chat")
def chat_info() -> dict[str, str]:
    return {"status": "ok", "method": "POST", "endpoint": "/api/chat"}


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    out = _call_brain(req.message)
    out = validate_output(out)

    policy_result = _apply_policy(out)

    proposed = _actions_to_dicts(out) if policy_result.allowed else []

    return ChatResponse(
        reply=out.reply,
        mode=req.mode.upper(),
        policy=policy_result,
        proposed_actions=proposed,
    )