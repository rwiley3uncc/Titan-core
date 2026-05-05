from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from titan_core.agent_memory import get_action_summary
from titan_core.action_log import load_action_log, log_action, make_action_log_entry
from titan_core.executor import execute_action

router = APIRouter()


@router.post("/execute")
def execute(action: dict):
    args = action.get("args", {}) if isinstance(action.get("args", {}), dict) else {}
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


@router.get("/action-log")
def get_action_log() -> list[dict]:
    entries = load_action_log()
    return [asdict(entry) for entry in entries[-20:]]


@router.get("/agent-memory")
def agent_memory() -> dict:
    return get_action_summary()
