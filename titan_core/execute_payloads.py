from __future__ import annotations

from titan_core.agent import AgentAction, AgentPlan


def action_args(action: dict) -> dict:
    return action.get("args", {}) if isinstance(action.get("args", {}), dict) else {}


def coerce_plan(plan_id: str, actions: list[dict]) -> AgentPlan:
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


def agent_action_to_dict(action: AgentAction, user_message: str) -> dict:
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


def next_pending_index(actions: list[dict]) -> int | None:
    for index, action in enumerate(actions):
        if str(action.get("status") or "pending").strip().lower() == "pending":
            return index
    return None
