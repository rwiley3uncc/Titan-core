from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from titan_core.agent import AgentAction, AgentPlan, SAFE_ACTIONS, is_plan_complete
from titan_core.agent_memory import get_action_summary
from titan_core.action_log import load_action_log, log_action, make_action_log_entry
from titan_core.executor import execute_action

router = APIRouter()


def _action_args(action: dict) -> dict:
    return action.get("args", {}) if isinstance(action.get("args", {}), dict) else {}


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
        if status not in {"approved", "cancelled", "executed", "failed"}:
            raise HTTPException(status_code=400, detail="client_execution.status must be approved, cancelled, executed, or failed.")
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


@router.post("/plan/approve-next")
def approve_next_plan_step(payload: dict) -> dict:
    plan_id = str(payload.get("plan_id") or "")
    actions = payload.get("actions")

    if not plan_id:
        raise HTTPException(status_code=400, detail="plan_id is required.")
    if not isinstance(actions, list):
        raise HTTPException(status_code=400, detail="actions must be a list.")

    updated_actions: list[dict] = []
    next_pending_index: int | None = None

    for index, item in enumerate(actions):
        if isinstance(item, dict):
            action = dict(item)
            action["status"] = str(action.get("status") or "pending").strip().lower()
            updated_actions.append(action)
            if next_pending_index is None and action["status"] == "pending":
                next_pending_index = index

    if next_pending_index is None:
        plan = AgentPlan(
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
                for action in updated_actions
            ],
        )
        return {"updated_actions": updated_actions, "plan_complete": is_plan_complete(plan)}

    target_action = updated_actions[next_pending_index]
    result = _execute_or_approve_action(target_action)
    target_action["status"] = str(result.get("action_status") or target_action.get("status") or "pending").lower()
    plan = AgentPlan(
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
            for action in updated_actions
        ],
    )
    return {"updated_actions": updated_actions, "plan_complete": is_plan_complete(plan)}


@router.get("/action-log")
def get_action_log() -> list[dict]:
    entries = load_action_log()
    return [asdict(entry) for entry in entries[-20:]]


@router.get("/agent-memory")
def agent_memory() -> dict:
    return get_action_summary()
