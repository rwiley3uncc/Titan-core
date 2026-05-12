from __future__ import annotations

from titan_core.action_log import log_action, make_action_log_entry
from titan_core.approval_log import emit_approval_request
from titan_core.event_log import emit_battlebuddy_event


def log_action_state(
    *,
    action_id: str,
    user_message: str,
    action_name: str,
    payload: dict,
    status: str,
    approved: bool,
    executed: bool,
    result: str,
) -> None:
    log_action(
        make_action_log_entry(
            action_id=action_id,
            user_message=user_message,
            action_name=action_name,
            payload=payload,
            status=status,
            approved=approved,
            executed=executed,
            result=result,
        )
    )


def emit_blocked_action_records(*, action_id: str, action_name: str, payload: dict) -> None:
    emit_approval_request(
        source="battlebuddy",
        subsystem="titan_core",
        title=f"Blocked action request: {action_name}",
        summary="A constrained action request was blocked because it is outside the current allow-list.",
        requested_action=action_name,
        risk="high",
        confidence=1.0,
        requires_confirmation=True,
        status="blocked",
        created_by="battlebuddy",
        metadata={
            "action_id": action_id,
            "app": payload.get("app"),
            "implemented": payload.get("implemented"),
            "requires_approval": payload.get("requires_approval"),
        },
    )
    emit_battlebuddy_event(
        subsystem="titan_core",
        severity="WARN",
        event_type="constrained_action_blocked",
        summary=f"Constrained action blocked: {action_name}.",
        details="Action is outside the current allow-list.",
        confidence=1.0,
        risk="medium",
        requires_approval=True,
        approved=True,
        status="failed",
    )


def emit_allowed_action_event(action_name: str) -> None:
    emit_battlebuddy_event(
        subsystem="titan_core",
        severity="NOTICE",
        event_type="constrained_action_allowed",
        summary=f"Constrained action allowed for execution: {action_name}.",
        details="Action is inside the current allow-list and proceeding through the constrained executor.",
        confidence=1.0,
        risk="medium",
        requires_approval=True,
        approved=True,
        status="approved",
    )


def emit_action_request_event(*, action_name: str, client_execution_present: bool) -> None:
    emit_battlebuddy_event(
        subsystem="titan_core",
        severity="INFO",
        event_type="constrained_action_requested",
        summary=f"Constrained action execution requested: {action_name}.",
        details=f"Client execution payload present: {client_execution_present}.",
        confidence=1.0,
        risk="medium",
        requires_approval=True,
        approved=False,
        status="pending",
    )


def emit_client_report_event(*, action_name: str, status: str) -> None:
    emit_battlebuddy_event(
        subsystem="titan_core",
        severity="NOTICE" if status in {"approved", "executed"} else "WARN",
        event_type="constrained_action_client_reported",
        summary=f"Client reported constrained action status: {status}.",
        details=f"Action: {action_name}.",
        confidence=0.9,
        risk="medium",
        requires_approval=True,
        approved=status in {"approved", "executed"},
        status="completed" if status in {"approved", "executed"} else "failed",
    )


def emit_execution_failure_event(*, action_name: str, failure_type: str) -> None:
    emit_battlebuddy_event(
        subsystem="titan_core",
        severity="ERROR",
        event_type="constrained_action_failed",
        summary=f"Constrained action failed: {action_name}.",
        details=f"Failure type: {failure_type}.",
        confidence=1.0,
        risk="high",
        requires_approval=True,
        approved=True,
        status="failed",
    )


def emit_execution_result_event(*, action_name: str, success: bool, executor_status: str) -> None:
    emit_battlebuddy_event(
        subsystem="titan_core",
        severity="OK" if success else "ERROR",
        event_type="constrained_action_executed" if success else "constrained_action_failed",
        summary=(
            f"Constrained action executed: {action_name}."
            if success else
            f"Constrained action returned a non-executed result: {action_name}."
        ),
        details=f"Executor status: {executor_status}.",
        confidence=1.0 if success else 0.8,
        risk="medium" if success else "high",
        requires_approval=True,
        approved=True,
        status="completed" if success else "failed",
    )
