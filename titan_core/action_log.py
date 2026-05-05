"""
Titan Core - Action Log
-----------------------

Append-only logging for proposed and approved Titan actions.

This keeps a simple transparent record of what Titan proposed, whether the
user approved it, and what happened when it executed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json


ACTION_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "action_log.json"


@dataclass
class ActionLogEntry:
    timestamp: str
    action_id: str
    user_message: str
    action_name: str
    status: str = "pending"
    payload: dict[str, Any] = field(default_factory=dict)
    approved: bool = False
    executed: bool = False
    result: str = ""


def _ensure_log_file() -> None:
    ACTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ACTION_LOG_PATH.exists():
        ACTION_LOG_PATH.write_text("", encoding="utf-8")


def load_action_log() -> list[ActionLogEntry]:
    _ensure_log_file()
    try:
        raw = ACTION_LOG_PATH.read_text(encoding="utf-8")
    except OSError:
        return []

    if not raw.strip():
        return []

    entries: list[ActionLogEntry] = []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    entries.append(
                        _coerce_log_entry(item)
                    )
            return entries
    except json.JSONDecodeError:
        pass

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        entries.append(_coerce_log_entry(item))
    return entries


def _coerce_log_entry(item: dict[str, Any]) -> ActionLogEntry:
    return ActionLogEntry(
        timestamp=str(item.get("timestamp", "")),
        action_id=str(item.get("action_id") or item.get("timestamp") or ""),
        user_message=str(item.get("user_message", "")),
        action_name=str(item.get("action_name", "")),
        status=_coerce_status(item),
        payload=item.get("payload", {}) if isinstance(item.get("payload", {}), dict) else {},
        approved=bool(item.get("approved", False)),
        executed=bool(item.get("executed", False)),
        result=str(item.get("result", "")),
    )


def _coerce_status(item: dict[str, Any]) -> str:
    status = str(item.get("status", "")).strip().lower()
    if status in {"pending", "approved", "cancelled", "executed", "failed"}:
        return status
    approved = bool(item.get("approved", False))
    executed = bool(item.get("executed", False))
    result = str(item.get("result", "")).strip().lower()
    if executed:
        return "executed"
    if approved:
        return "approved"
    if "cancel" in result:
        return "cancelled"
    if result and result not in {"proposed", "pending"}:
        return "failed"
    return "pending"


def log_action(entry: ActionLogEntry) -> None:
    _ensure_log_file()
    try:
        with ACTION_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), ensure_ascii=True) + "\n")
    except OSError:
        return


def make_action_log_entry(
    *,
    action_id: str,
    user_message: str,
    action_name: str,
    status: str = "pending",
    payload: dict[str, Any] | None = None,
    approved: bool = False,
    executed: bool = False,
    result: str = "",
) -> ActionLogEntry:
    return ActionLogEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        action_id=action_id,
        user_message=user_message,
        action_name=action_name,
        status=status,
        payload=payload or {},
        approved=approved,
        executed=executed,
        result=result,
    )
