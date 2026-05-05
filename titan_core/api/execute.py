from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from titan_core.agent import AgentAction, AgentPlan, SAFE_ACTIONS, get_next_step_message, is_plan_complete, plan_agent_action, validate_agent_action
from titan_core.agent_memory import get_action_summary
from titan_core.action_log import load_action_log, log_action, make_action_log_entry
from titan_core.executor import execute_action

router = APIRouter()


def _action_args(action: dict) -> dict:
    return action.get("args", {}) if isinstance(action.get("args", {}), dict) else {}


def _coerce_plan(plan_id: str, actions: list[dict]) -> AgentPlan:
    return AgentPlan(
        plan_id=plan_id,
        summary="",
        actions=[
            AgentAction(
                name=str(action.get("type") or action.get("action") or "unknown_action"),
                description=str(action.get("label") or action.get("type") or "Unknown action"),
                action_id=str(action.get("action_id") or ""),
                created_at=float(action.get("created_at") or 0.0),
                status=str(action.get("status") or "pending"),
                confidence=float(action.get("confidence") or 0.0),
                reason=str(action.get("reason") or ""),
                payload=action.get("args", {}) if isinstance(action.get("args", {}), dict) else {},
            )
            for action in actions
        ],
    )


def _agent_action_to_dict(action: AgentAction, user_message: str) -> dict:
    metadata = dict(action.payload)
    metadata["implemented"] = True
    metadata["requires_approval"] = action.requires_approval
    return {
        "type": action.name,
        "label": action.description,
        "action_id": action.action_id,
        "created_at": action.created_at,
        "status": action.status,
        "confidence": action.confidence,
        "reason": action.reason,
        "app": metadata.get("app"),
        "args": {
            **metadata,
            "log_user_message": user_message,
        },
    }


def _execute_or_approve_action(action: dict) -> dict:
    args = _action_args(action)
    user_message = str(args.get("log_user_message", ""))
    action_name = str(action.get("type") or action.get("action") or "unknown_action")
    payload = dict(args)
    action_id = str(action.get("action_id") or "")

    if not action_id:
        raise HTTPException(status_code=400, detail="action_id is required.")

    log_action(
        make_action_log_entry(
            action_id=action_id,
            user_message=user_message,
            action_name=action_name,
            payload=payload,
            status="approved",
            approved=True,
            executed=False,
            result="approved by user",
        )
    )

    if action_name not in SAFE_ACTIONS:
        return {
            "status": "approved",
            "message": "Action approved and awaiting future implementation.",
            "action_id": action_id,
            "action_status": "approved",
        }

    try:
        result = execute_action(action)
    except Exception as exc:
        error_message = str(exc) or "execution failed"
        log_action(
            make_action_log_entry(
                action_id=action_id,
                user_message=user_message,
                action_name=action_name,
                payload=payload,
                status="failed",
                approved=True,
                executed=False,
                result=error_message,
            )
        )
        return {"status": "error", "message": error_message, "action_id": action_id, "action_status": "failed"}

    success = result.get("status") == "executed"
    final_status = "executed" if success else "failed"
    log_action(
        make_action_log_entry(
            action_id=action_id,
            user_message=user_message,
            action_name=action_name,
            payload=payload,
            status=final_status,
            approved=True,
            executed=success,
            result=result.get("message") or result.get("status", ""),
        )
    )
    return {
        **result,
        "action_id": action_id,
        "action_status": final_status,
    }


@router.post("/execute")
def execute(action: dict):
    args = _action_args(action)
    user_message = str(args.get("log_user_message", ""))
    action_name = str(action.get("type") or action.get("action") or "unknown_action")
    payload = dict(args)
    action_id = str(action.get("action_id") or "")

    if not action_id:
        raise HTTPException(status_code=400, detail="action_id is required.")

    client_execution = action.get("client_execution")
    if isinstance(client_execution, dict):
        status = str(client_execution.get("status") or "").strip().lower()
        result = str(client_execution.get("result", ""))
        if status not in {"approved", "cancelled", "executed", "failed", "skipped", "replaced"}:
            raise HTTPException(status_code=400, detail="client_execution.status must be approved, cancelled, executed, failed, skipped, or replaced.")
        log_action(
            make_action_log_entry(
                action_id=action_id,
                user_message=user_message,
                action_name=action_name,
                payload=payload,
                status=status,
                approved=status in {"approved", "executed"},
                executed=status == "executed",
                result=result,
            )
        )
        return {
            "status": "logged",
            "message": result or f"Action status recorded as {status}.",
            "action_id": action_id,
            "action_status": status,
        }
    return _execute_or_approve_action(action)


def _next_pending_index(actions: list[dict]) -> int | None:
    for index, action in enumerate(actions):
        if str(action.get("status") or "pending").strip().lower() == "pending":
            return index
    return None


@router.post("/plan/approve-next")
def approve_next_plan_step(payload: dict) -> dict:
    plan_id = str(payload.get("plan_id") or "")
    actions = payload.get("actions")

    if not plan_id:
        raise HTTPException(status_code=400, detail="plan_id is required.")
    if not isinstance(actions, list):
        raise HTTPException(status_code=400, detail="actions must be a list.")

    updated_actions: list[dict] = []

    for index, item in enumerate(actions):
        if isinstance(item, dict):
            action = dict(item)
            action["status"] = str(action.get("status") or "pending").strip().lower()
            updated_actions.append(action)
    next_pending_index = _next_pending_index(updated_actions)

    if next_pending_index is None:
        plan = _coerce_plan(plan_id, updated_actions)
        return {
            "updated_actions": updated_actions,
            "plan_complete": is_plan_complete(plan),
            "next_step_message": get_next_step_message(plan),
        }

    target_action = updated_actions[next_pending_index]
    result = _execute_or_approve_action(target_action)
    target_action["status"] = str(result.get("action_status") or target_action.get("status") or "pending").lower()
    plan = _coerce_plan(plan_id, updated_actions)
    return {
        "updated_actions": updated_actions,
        "plan_complete": is_plan_complete(plan),
        "next_step_message": get_next_step_message(plan),
    }


@router.post("/plan/skip-next")
def skip_next_plan_step(payload: dict) -> dict:
    plan_id = str(payload.get("plan_id") or "")
    actions = payload.get("actions")

    if not plan_id:
        raise HTTPException(status_code=400, detail="plan_id is required.")
    if not isinstance(actions, list):
        raise HTTPException(status_code=400, detail="actions must be a list.")

    updated_actions: list[dict] = []
    for item in actions:
        if isinstance(item, dict):
            action = dict(item)
            action["status"] = str(action.get("status") or "pending").strip().lower()
            updated_actions.append(action)

    next_pending_index = _next_pending_index(updated_actions)
    if next_pending_index is not None:
        target_action = updated_actions[next_pending_index]
        target_action["status"] = "skipped"
        args = _action_args(target_action)
        log_action(
            make_action_log_entry(
                action_id=str(target_action.get("action_id") or ""),
                user_message=str(args.get("log_user_message", "")),
                action_name=str(target_action.get("type") or target_action.get("action") or "unknown_action"),
                payload=dict(args),
                status="skipped",
                approved=False,
                executed=False,
                result="skipped by user",
            )
        )

    plan = _coerce_plan(plan_id, updated_actions)
    return {
        "updated_actions": updated_actions,
        "plan_complete": is_plan_complete(plan),
        "next_step_message": get_next_step_message(plan),
    }


@router.post("/plan/replace-next")
def replace_next_plan_step(payload: dict) -> dict:
    plan_id = str(payload.get("plan_id") or "")
    actions = payload.get("actions")
    user_message = str(payload.get("user_message") or "").strip()

    if not plan_id:
        raise HTTPException(status_code=400, detail="plan_id is required.")
    if not isinstance(actions, list):
        raise HTTPException(status_code=400, detail="actions must be a list.")
    if not user_message:
        raise HTTPException(status_code=400, detail="user_message is required.")

    replacement_action = plan_agent_action(user_message)
    if not validate_agent_action(replacement_action):
        raise HTTPException(status_code=400, detail="No valid safe replacement action was found.")

    updated_actions: list[dict] = []
    for item in actions:
        if isinstance(item, dict):
            action = dict(item)
            action["status"] = str(action.get("status") or "pending").strip().lower()
            updated_actions.append(action)

    next_pending_index = _next_pending_index(updated_actions)
    if next_pending_index is None:
        plan = _coerce_plan(plan_id, updated_actions)
        return {
            "updated_actions": updated_actions,
            "plan_complete": is_plan_complete(plan),
            "next_step_message": get_next_step_message(plan),
            "replaced": False,
        }

    old_action = updated_actions[next_pending_index]
    old_action["status"] = "replaced"
    old_args = _action_args(old_action)
    log_action(
        make_action_log_entry(
            action_id=str(old_action.get("action_id") or ""),
            user_message=str(old_args.get("log_user_message", "")),
            action_name=str(old_action.get("type") or old_action.get("action") or "unknown_action"),
            payload=dict(old_args),
            status="replaced",
            approved=False,
            executed=False,
            result="replaced by user",
        )
    )

    replacement_payload = _agent_action_to_dict(replacement_action, user_message)
    log_entry = make_action_log_entry(
        action_id=str(replacement_payload.get("action_id") or ""),
        user_message=user_message,
        action_name=str(replacement_payload.get("type") or "unknown_action"),
        payload=_action_args(replacement_payload),
        status="pending",
        approved=False,
        executed=False,
        result="proposed",
    )
    replacement_payload["args"]["log_timestamp"] = log_entry.timestamp
    log_action(log_entry)

    updated_actions.insert(next_pending_index + 1, replacement_payload)
    plan = _coerce_plan(plan_id, updated_actions)
    return {
        "updated_actions": updated_actions,
        "plan_complete": is_plan_complete(plan),
        "next_step_message": get_next_step_message(plan),
        "replaced": True,
    }


@router.get("/action-log")
def get_action_log() -> list[dict]:
    entries = load_action_log()
    return [asdict(entry) for entry in entries[-20:]]


@router.get("/agent-memory")
def agent_memory() -> dict:
    return get_action_summary()
