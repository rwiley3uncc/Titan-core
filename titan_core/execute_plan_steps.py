from __future__ import annotations

from fastapi import HTTPException

from titan_core.action_log import make_action_log_entry
from titan_core.agent import AgentAction, get_next_step_message, is_plan_complete
from titan_core.execute_payloads import action_args, agent_action_to_dict, coerce_plan, next_pending_index
from titan_core.execute_side_effects import emit_client_report_event, log_action_state

ALLOWED_CLIENT_EXECUTION_STATUSES = {"approved", "cancelled", "executed", "failed", "skipped", "replaced"}


def normalize_actions(actions: list[dict]) -> list[dict]:
    normalized_actions: list[dict] = []
    for item in actions:
        if isinstance(item, dict):
            action = dict(item)
            action["status"] = str(action.get("status") or "pending").strip().lower()
            normalized_actions.append(action)
    return normalized_actions


def log_client_execution_report(*, action: dict, client_execution: dict) -> dict:
    status = str(client_execution.get("status") or "").strip().lower()
    result = str(client_execution.get("result", ""))
    if status not in ALLOWED_CLIENT_EXECUTION_STATUSES:
        raise HTTPException(status_code=400, detail="client_execution.status must be approved, cancelled, executed, failed, skipped, or replaced.")

    args = action_args(action)
    action_name = str(action.get("type") or action.get("action") or "unknown_action")
    log_action_state(
        action_id=str(action.get("action_id") or ""),
        user_message=str(args.get("log_user_message", "")),
        action_name=action_name,
        payload=dict(args),
        status=status,
        approved=status in {"approved", "executed"},
        executed=status == "executed",
        result=result,
    )
    emit_client_report_event(action_name=action_name, status=status)
    return {
        "status": "logged",
        "message": result or f"Action status recorded as {status}.",
        "action_id": str(action.get("action_id") or ""),
        "action_status": status,
    }


def skip_next_pending_action(actions: list[dict]) -> list[dict]:
    pending_index = next_pending_index(actions)
    if pending_index is None:
        return actions

    target_action = actions[pending_index]
    target_action["status"] = "skipped"
    args = action_args(target_action)
    log_action_state(
        action_id=str(target_action.get("action_id") or ""),
        user_message=str(args.get("log_user_message", "")),
        action_name=str(target_action.get("type") or target_action.get("action") or "unknown_action"),
        payload=dict(args),
        status="skipped",
        approved=False,
        executed=False,
        result="skipped by user",
    )
    return actions


def get_next_pending_action(actions: list[dict]) -> tuple[int | None, dict | None]:
    pending_index = next_pending_index(actions)
    if pending_index is None:
        return None, None
    return pending_index, actions[pending_index]


def apply_next_pending_action_result(actions: list[dict], result: dict) -> list[dict]:
    pending_index, target_action = get_next_pending_action(actions)
    if pending_index is None or target_action is None:
        return actions

    target_action["status"] = str(result.get("action_status") or target_action.get("status") or "pending").lower()
    return actions


def replace_next_pending_action(*, actions: list[dict], replacement_action: AgentAction, user_message: str) -> tuple[list[dict], bool]:
    pending_index = next_pending_index(actions)
    if pending_index is None:
        return actions, False

    old_action = actions[pending_index]
    old_action["status"] = "replaced"
    old_args = action_args(old_action)
    log_action_state(
        action_id=str(old_action.get("action_id") or ""),
        user_message=str(old_args.get("log_user_message", "")),
        action_name=str(old_action.get("type") or old_action.get("action") or "unknown_action"),
        payload=dict(old_args),
        status="replaced",
        approved=False,
        executed=False,
        result="replaced by user",
    )

    replacement_payload = agent_action_to_dict(replacement_action, user_message)
    log_entry = make_action_log_entry(
        action_id=str(replacement_payload.get("action_id") or ""),
        user_message=user_message,
        action_name=str(replacement_payload.get("type") or "unknown_action"),
        payload=action_args(replacement_payload),
        status="pending",
        approved=False,
        executed=False,
        result="proposed",
    )
    replacement_payload["args"]["log_timestamp"] = log_entry.timestamp
    log_action_state(
        action_id=log_entry.action_id,
        user_message=log_entry.user_message,
        action_name=log_entry.action_name,
        payload=log_entry.payload,
        status=log_entry.status,
        approved=log_entry.approved,
        executed=log_entry.executed,
        result=log_entry.result,
    )

    actions.insert(pending_index + 1, replacement_payload)
    return actions, True


def build_plan_response(*, plan_id: str, actions: list[dict], replaced: bool | None = None) -> dict:
    plan = coerce_plan(plan_id, actions)
    response = {
        "updated_actions": actions,
        "plan_complete": is_plan_complete(plan),
        "next_step_message": get_next_step_message(plan),
    }
    if replaced is not None:
        response["replaced"] = replaced
    return response
