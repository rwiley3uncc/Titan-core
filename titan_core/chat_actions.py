from __future__ import annotations

import time
from uuid import uuid4

from titan_core.action_log import load_action_log, log_action, make_action_log_entry
from titan_core.agent import AgentAction, AgentPlan, get_next_step_message
from titan_core.approval_log import emit_approval_request
from titan_core.event_log import emit_battlebuddy_event, summarize_action_names
from titan_core.schemas import ChatResponse, ProposedAction, ProposedPlan

from .chat_mode import normalize_text


REPLACEMENT_INTENT_TOKENS = ("instead", "actually", "do this instead", "replace")
SKIP_INTENT_TOKENS = ("skip this step", "skip it", "skip current step", "skip this", "move past this")
APPROVE_NEXT_INTENT_TOKENS = ("approve next", "approve this step", "go ahead", "do it", "run next step", "continue")


def _action(action_type: str, label: str, **args) -> ProposedAction:
    return ProposedAction(type=action_type, label=label, args=args)


def _agent_action_to_proposed_action(action: AgentAction) -> ProposedAction:
    args = dict(action.payload)
    args["implemented"] = True
    args["requires_approval"] = action.requires_approval
    return ProposedAction(
        type=action.name,
        label=action.description,
        action_id=action.action_id,
        created_at=action.created_at,
        status=action.status,
        confidence=action.confidence,
        reason=action.reason,
        args=args,
    )


def _agent_plan_to_proposed_plan(plan: AgentPlan) -> ProposedPlan:
    return ProposedPlan(
        plan_id=plan.plan_id,
        created_at=plan.created_at,
        summary=plan.summary,
        current_step_index=plan.current_step_index,
        next_step_message=get_next_step_message(plan),
        actions=[_agent_action_to_proposed_action(action) for action in plan.actions],
    )


def _is_replacement_intent(text: str) -> bool:
    normalized = normalize_text(text)
    return any(token in normalized for token in REPLACEMENT_INTENT_TOKENS)


def _is_skip_intent(text: str) -> bool:
    normalized = normalize_text(text)
    return any(token in normalized for token in SKIP_INTENT_TOKENS)


def _is_approve_next_intent(text: str) -> bool:
    normalized = normalize_text(text)
    return any(token in normalized for token in APPROVE_NEXT_INTENT_TOKENS)


def _active_plan_pending_action_type(active_plan: dict | None) -> str:
    if not isinstance(active_plan, dict):
        return ""
    actions = active_plan.get("actions")
    if not isinstance(actions, list):
        return ""
    for action in actions:
        if isinstance(action, dict) and str(action.get("status") or "").strip().lower() == "pending":
            return str(action.get("type") or action.get("action") or "")
    return ""


def _suggestion_stats(current_step_name: str, replacement_name: str) -> tuple[int, int]:
    skip_count = 0
    approve_count = 0
    for entry in load_action_log():
        if entry.action_name == current_step_name and entry.status == "skipped":
            skip_count += 1
        if entry.action_name == replacement_name and entry.status == "approved":
            approve_count += 1
    return skip_count, approve_count


def _ensure_action_metadata(proposed: ProposedAction) -> ProposedAction:
    proposed.action_id = proposed.action_id or str(uuid4())
    proposed.created_at = proposed.created_at if proposed.created_at is not None else time.time()
    proposed.status = proposed.status or "pending"
    return proposed


def _finalize_chat_response(user_message: str, response: ChatResponse) -> ChatResponse:
    if response.proposed_plan:
        for planned_action in response.proposed_plan.actions:
            _ensure_action_metadata(planned_action)
        response.proposed_actions = list(response.proposed_plan.actions)

    for proposed in response.proposed_actions:
        _ensure_action_metadata(proposed)
        metadata = dict(proposed.args or {})
        if metadata.get("log_timestamp"):
            continue
        entry = make_action_log_entry(
            action_id=proposed.action_id or "",
            user_message=user_message,
            action_name=proposed.type,
            status="pending",
            payload=metadata,
            approved=False,
            executed=False,
            result="proposed",
        )
        metadata["log_timestamp"] = entry.timestamp
        metadata["log_user_message"] = user_message
        proposed.args = metadata
        proposed.status = "pending"
        log_action(entry)

    if response.proposed_actions:
        emit_battlebuddy_event(
            subsystem="battlebuddy",
            severity="NOTICE",
            event_type="proposed_action_created",
            summary=f"Generated {len(response.proposed_actions)} proposed action(s).",
            details=f"Action types: {summarize_action_names(response.proposed_actions)}.",
            confidence=max([float(getattr(action, "confidence", 0.0) or 0.0) for action in response.proposed_actions], default=0.0),
            risk="medium",
            requires_approval=True,
            approved=False,
            status="pending",
        )
        for proposed_action in response.proposed_actions[:5]:
            emit_approval_request(
                source="battlebuddy",
                subsystem="battlebuddy",
                title=f"Review proposed action: {proposed_action.type}",
                summary="BattleBuddy proposed a constrained action for local review.",
                requested_action=proposed_action.type,
                risk="medium",
                confidence=float(getattr(proposed_action, "confidence", 0.0) or 0.0),
                requires_confirmation=True,
                status="pending",
                created_by="battlebuddy",
                metadata={
                    "label": proposed_action.label,
                    "action_id": proposed_action.action_id,
                    "app": proposed_action.app,
                },
            )
    return response
