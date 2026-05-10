from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from titan_core.titan_shared_imports import ensure_titan_shared_on_path

ensure_titan_shared_on_path()

try:  # pragma: no cover - safe runtime fallback
    from titan_shared.contracts.approval_request import ApprovalRequest, ApprovalRequestStatus
except Exception:  # pragma: no cover - safe runtime fallback
    ApprovalRequest = None
    ApprovalRequestStatus = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APPROVALS_DIR = PROJECT_ROOT / "data" / "approvals"
APPROVAL_LOG_PATH = APPROVALS_DIR / "approval_requests.jsonl"
DEDUP_SCAN_LIMIT = 50
SENSITIVE_METADATA_TOKENS = {
    "authorization",
    "body",
    "content",
    "cookie",
    "file_content",
    "log_user_message",
    "message",
    "prompt",
    "secret",
    "token",
    "user_message",
}


def _status_value(value: str | None) -> str:
    normalized = str(value or "pending").strip().lower()
    if ApprovalRequestStatus is None:
        return normalized or "pending"

    allowed = {status.value for status in ApprovalRequestStatus}
    if normalized in allowed:
        return normalized
    return ApprovalRequestStatus.PENDING.value


def _read_recent_lines(log_path: Path, limit: int = DEDUP_SCAN_LIMIT) -> list[str]:
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    if limit <= 0:
        return lines
    return lines[-limit:]


def _is_sensitive_metadata_key(value: object) -> bool:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return False
    return any(token in normalized for token in SENSITIVE_METADATA_TOKENS)


def _safe_metadata(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}

    safe_metadata: dict[str, Any] = {}
    for key, item in value.items():
        if _is_sensitive_metadata_key(key):
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            safe_metadata[str(key)] = item
        elif isinstance(item, Mapping):
            nested: dict[str, Any] = {}
            for nested_key, nested_item in item.items():
                if _is_sensitive_metadata_key(nested_key):
                    continue
                if isinstance(nested_item, (str, int, float, bool)) or nested_item is None:
                    nested[str(nested_key)] = nested_item
            if nested:
                safe_metadata[str(key)] = nested
    return safe_metadata


def _dedupe_key(
    *,
    requested_action: str,
    status: str,
    metadata: Mapping[str, Any],
) -> str:
    action_id = str(metadata.get("action_id") or "").strip()
    if action_id:
        return f"{requested_action}|{status}|{action_id}"

    app = str(metadata.get("app") or "").strip()
    label = str(metadata.get("label") or "").strip()
    return f"{requested_action}|{status}|{app}|{label}"


def _is_recent_duplicate(
    log_path: Path,
    *,
    requested_action: str,
    status: str,
    metadata: Mapping[str, Any],
) -> bool:
    if not log_path.exists():
        return False

    target_key = _dedupe_key(
        requested_action=requested_action,
        status=status,
        metadata=metadata,
    )
    if not target_key.strip("|"):
        return False

    for line in reversed(_read_recent_lines(log_path)):
        payload = line.strip()
        if not payload:
            continue
        try:
            existing = ApprovalRequest.from_json(payload)
        except Exception:
            continue

        existing_key = _dedupe_key(
            requested_action=existing.requested_action,
            status=existing.status.value if hasattr(existing.status, "value") else str(existing.status),
            metadata=existing.metadata,
        )
        if existing_key == target_key:
            return True

    return False


def emit_approval_request(
    *,
    title: str,
    summary: str,
    requested_action: str,
    risk: str = "unknown",
    confidence: float = 0.0,
    requires_confirmation: bool = True,
    status: str = "pending",
    source: str = "battlebuddy",
    subsystem: str = "battlebuddy",
    created_by: str = "battlebuddy",
    related_event_id: str = "",
    metadata: Mapping[str, Any] | None = None,
    log_path: str | Path | None = None,
) -> bool:
    if ApprovalRequest is None:
        return False

    try:
        target_path = Path(log_path) if log_path is not None else APPROVAL_LOG_PATH
        target_path.parent.mkdir(parents=True, exist_ok=True)
        safe_metadata = _safe_metadata(metadata)
        normalized_status = _status_value(status)
        if _is_recent_duplicate(
            target_path,
            requested_action=requested_action,
            status=normalized_status,
            metadata=safe_metadata,
        ):
            return True
        request = ApprovalRequest(
            source=source,
            subsystem=subsystem,
            title=title,
            summary=summary,
            requested_action=requested_action,
            risk=risk,
            confidence=confidence,
            requires_confirmation=requires_confirmation,
            status=normalized_status,
            created_by=created_by,
            related_event_id=related_event_id,
            metadata=safe_metadata,
        )
        with target_path.open("a", encoding="utf-8") as handle:
            handle.write(request.to_json() + "\n")
        return True
    except Exception:
        return False
