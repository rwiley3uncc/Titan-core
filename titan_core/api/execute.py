from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from titan_core.agent import SAFE_ACTIONS, plan_agent_action, validate_agent_action
from titan_core.agent_memory import get_action_summary
from titan_core.action_log import load_action_log
from titan_core.execute_payloads import action_args
from titan_core.execute_plan_steps import (
    apply_next_pending_action_result,
    build_plan_response,
    get_next_pending_action,
    log_client_execution_report,
    normalize_actions,
    replace_next_pending_action,
    skip_next_pending_action,
)
from titan_core.execute_side_effects import (
    emit_action_request_event,
    emit_allowed_action_event,
    emit_blocked_action_records,
    emit_execution_failure_event,
    emit_execution_result_event,
    log_action_state,
)
from titan_core.executor import execute_action

router = APIRouter()


def _execute_or_approve_action(action: dict) -> dict:
    args = action_args(action)
    user_message = str(args.get("log_user_message", ""))
    action_name = str(action.get("type") or action.get("action") or "unknown_action")
    payload = dict(args)
    action_id = str(action.get("action_id") or "")

    if not action_id:
        raise HTTPException(status_code=400, detail="action_id is required.")

    log_action_state(
        action_id=action_id,
        user_message=user_message,
        action_name=action_name,
        payload=payload,
        status="approved",
        approved=True,
        executed=False,
        result="approved by user",
    )

    if action_name not in SAFE_ACTIONS:
        emit_blocked_action_records(action_id=action_id, action_name=action_name, payload=payload)
        return {
            "status": "approved",
            "message": "Action approved and awaiting future implementation.",
            "action_id": action_id,
            "action_status": "approved",
        }

    emit_allowed_action_event(action_name)

    try:
        result = execute_action(action)
    except Exception as exc:
        error_message = str(exc) or "execution failed"
        emit_execution_failure_event(action_name=action_name, failure_type=type(exc).__name__)
        log_action_state(
            action_id=action_id,
            user_message=user_message,
            action_name=action_name,
            payload=payload,
            status="failed",
            approved=True,
            executed=False,
            result=error_message,
        )
        return {"status": "error", "message": error_message, "action_id": action_id, "action_status": "failed"}

    success = result.get("status") == "executed"
    final_status = "executed" if success else "failed"
    emit_execution_result_event(
        action_name=action_name,
        success=success,
        executor_status=str(result.get("status", "unknown")),
    )
    log_action_state(
        action_id=action_id,
        user_message=user_message,
        action_name=action_name,
        payload=payload,
        status=final_status,
        approved=True,
        executed=success,
        result=result.get("message") or result.get("status", ""),
    )
    return {
        **result,
        "action_id": action_id,
        "action_status": final_status,
    }


@router.post("/execute")
def execute(action: dict):
    args = action_args(action)
    user_message = str(args.get("log_user_message", ""))
    action_name = str(action.get("type") or action.get("action") or "unknown_action")
    payload = dict(args)
    action_id = str(action.get("action_id") or "")

    if not action_id:
        raise HTTPException(status_code=400, detail="action_id is required.")

    emit_action_request_event(
        action_name=action_name,
        client_execution_present=isinstance(action.get("client_execution"), dict),
    )

    client_execution = action.get("client_execution")
    if isinstance(client_execution, dict):
        return log_client_execution_report(action=action, client_execution=client_execution)
    return _execute_or_approve_action(action)


@router.post("/plan/approve-next")
def approve_next_plan_step(payload: dict) -> dict:
    plan_id = str(payload.get("plan_id") or "")
    actions = payload.get("actions")

    if not plan_id:
        raise HTTPException(status_code=400, detail="plan_id is required.")
    if not isinstance(actions, list):
        raise HTTPException(status_code=400, detail="actions must be a list.")

    updated_actions = normalize_actions(actions)
    pending_index, target_action = get_next_pending_action(updated_actions)

    if pending_index is None or target_action is None:
        return build_plan_response(plan_id=plan_id, actions=updated_actions)

    result = _execute_or_approve_action(target_action)
    updated_actions = apply_next_pending_action_result(updated_actions, result)
    return build_plan_response(plan_id=plan_id, actions=updated_actions)


@router.post("/plan/skip-next")
def skip_next_plan_step(payload: dict) -> dict:
    plan_id = str(payload.get("plan_id") or "")
    actions = payload.get("actions")

    if not plan_id:
        raise HTTPException(status_code=400, detail="plan_id is required.")
    if not isinstance(actions, list):
        raise HTTPException(status_code=400, detail="actions must be a list.")

    updated_actions = normalize_actions(actions)
    updated_actions = skip_next_pending_action(updated_actions)
    return build_plan_response(plan_id=plan_id, actions=updated_actions)


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

    updated_actions = normalize_actions(actions)

    pending_index, _ = get_next_pending_action(updated_actions)
    if pending_index is None:
        return build_plan_response(plan_id=plan_id, actions=updated_actions, replaced=False)

    updated_actions, replaced = replace_next_pending_action(
        actions=updated_actions,
        replacement_action=replacement_action,
        user_message=user_message,
    )
    return build_plan_response(plan_id=plan_id, actions=updated_actions, replaced=replaced)


@router.get("/action-log")
def get_action_log() -> list[dict]:
    entries = load_action_log()
    return [asdict(entry) for entry in entries[-20:]]


@router.get("/agent-memory")
def agent_memory() -> dict:
    return get_action_summary()
