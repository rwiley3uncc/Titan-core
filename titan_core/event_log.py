from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from titan_core.titan_shared_imports import ensure_titan_shared_on_path

ensure_titan_shared_on_path()

try:  # pragma: no cover - safe runtime fallback
    from titan_shared.contracts.titan_event import TitanEvent, TitanEventStatus
except Exception:  # pragma: no cover - safe runtime fallback
    TitanEvent = None
    TitanEventStatus = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENTS_DIR = PROJECT_ROOT / "data" / "events"
EVENT_LOG_PATH = EVENTS_DIR / "titan_events.jsonl"
EVENT_ARCHIVE_DIR = EVENTS_DIR / "archive"
DEFAULT_MAX_EVENT_COUNT = 1000
DEFAULT_MAX_EVENT_LOG_BYTES = 2 * 1024 * 1024


def _status_value(value: str | None) -> str:
    normalized = str(value or "recorded").strip().lower()
    if TitanEventStatus is None:
        return normalized or "recorded"

    allowed = {status.value for status in TitanEventStatus}
    if normalized in allowed:
        return normalized
    return TitanEventStatus.RECORDED.value


def _archive_trimmed_lines(lines: list[str], *, archive_dir: Path) -> None:
    if not lines:
        return

    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = archive_dir / f"titan_events_archive_{timestamp}.jsonl"
    with archive_path.open("a", encoding="utf-8") as handle:
        for line in lines:
            if line.strip():
                handle.write(line if line.endswith("\n") else f"{line}\n")


def enforce_event_log_retention(
    log_path: str | Path,
    *,
    max_events: int = DEFAULT_MAX_EVENT_COUNT,
    max_bytes: int = DEFAULT_MAX_EVENT_LOG_BYTES,
    archive_dir: str | Path | None = None,
) -> bool:
    target_path = Path(log_path)
    if not target_path.exists():
        return True

    safe_max_events = max(1, int(max_events))
    safe_max_bytes = max(1024, int(max_bytes))

    try:
        lines = target_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False

    trimmed_lines = list(lines)
    archived_lines: list[str] = []

    if len(trimmed_lines) > safe_max_events:
        overflow_count = len(trimmed_lines) - safe_max_events
        archived_lines.extend(trimmed_lines[:overflow_count])
        trimmed_lines = trimmed_lines[overflow_count:]

    def current_size_bytes() -> int:
        if not trimmed_lines:
            return 0
        return sum(len((line if line.endswith("\n") else f"{line}\n").encode("utf-8")) for line in trimmed_lines)

    while trimmed_lines and current_size_bytes() > safe_max_bytes:
        archived_lines.append(trimmed_lines.pop(0))

    if archived_lines:
        try:
            archive_target = Path(archive_dir) if archive_dir is not None else EVENT_ARCHIVE_DIR
            _archive_trimmed_lines(archived_lines, archive_dir=archive_target)
        except Exception:
            pass

    if len(trimmed_lines) == len(lines):
        return True

    try:
        payload = ""
        if trimmed_lines:
            payload = "\n".join(trimmed_lines) + "\n"
        target_path.write_text(payload, encoding="utf-8")
        return True
    except Exception:
        return False


def emit_battlebuddy_event(
    *,
    event_type: str,
    summary: str,
    severity: str = "INFO",
    details: str = "",
    confidence: float = 0.0,
    risk: str = "unknown",
    requires_approval: bool = False,
    approved: bool = False,
    status: str = "recorded",
    source: str = "battlebuddy",
    subsystem: str = "battlebuddy",
    log_path: str | Path | None = None,
    max_events: int = DEFAULT_MAX_EVENT_COUNT,
    max_bytes: int = DEFAULT_MAX_EVENT_LOG_BYTES,
    archive_dir: str | Path | None = None,
) -> bool:
    if TitanEvent is None:
        return False

    try:
        target_path = Path(log_path) if log_path is not None else EVENT_LOG_PATH
        target_path.parent.mkdir(parents=True, exist_ok=True)
        event = TitanEvent(
            source=source,
            subsystem=subsystem,
            severity=severity,
            event_type=event_type,
            summary=summary,
            details=details,
            confidence=confidence,
            risk=risk,
            requires_approval=requires_approval,
            approved=approved,
            status=_status_value(status),
        )
        with target_path.open("a", encoding="utf-8") as handle:
            handle.write(event.to_json() + "\n")
        try:
            enforce_event_log_retention(
                target_path,
                max_events=max_events,
                max_bytes=max_bytes,
                archive_dir=archive_dir,
            )
        except Exception:
            pass
        return True
    except Exception:
        return False


def summarize_action_names(actions: list[Any], *, limit: int = 3) -> str:
    names: list[str] = []
    for action in actions[:limit]:
        action_name = getattr(action, "type", None) or getattr(action, "name", None)
        if not action_name and isinstance(action, dict):
            action_name = action.get("type") or action.get("action")
        if action_name:
            names.append(str(action_name))
    return ", ".join(names) if names else "none"
