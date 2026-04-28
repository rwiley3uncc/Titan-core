from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from titan_core.schemas import CalendarSourceCreate, CalendarSourceRecord, CalendarSourceUpdate


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CALENDAR_SOURCES_PATH = DATA_DIR / "calendar_sources.json"
ALLOWED_CALENDAR_TYPES = {"canvas", "outlook", "other"}


def _default_sources() -> list[CalendarSourceRecord]:
    now = datetime.now().isoformat()
    return [
        CalendarSourceRecord(
            id="school_canvas",
            name="School Calendar",
            type="canvas",
            url="",
            enabled=False,
            created_at=now,
            updated_at=now,
        ),
        CalendarSourceRecord(
            id="personal_outlook",
            name="Personal Calendar",
            type="outlook",
            url="",
            enabled=False,
            created_at=now,
            updated_at=now,
        ),
    ]


def _normalize_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "calendar"


def _normalized_type(value: str | None) -> str:
    lowered = (value or "other").strip().lower()
    return lowered if lowered in ALLOWED_CALENDAR_TYPES else "other"


def _ensure_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CALENDAR_SOURCES_PATH.exists():
        _save_sources(_default_sources())


def _migrate_record(item: dict, created_at_fallback: str) -> CalendarSourceRecord | None:
    if not isinstance(item, dict):
        return None
    try:
        return CalendarSourceRecord(
            id=str(item.get("id") or _normalize_id(str(item.get("name") or "calendar"))),
            name=str(item.get("name") or "Calendar"),
            type=_normalized_type(item.get("type")),
            url=str(item.get("url") or ""),
            enabled=bool(item.get("enabled", False)),
            created_at=str(item.get("created_at") or created_at_fallback),
            updated_at=str(item.get("updated_at") or created_at_fallback),
        )
    except Exception:
        return None


def _load_sources() -> list[CalendarSourceRecord]:
    _ensure_store()
    raw = json.loads(CALENDAR_SOURCES_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        records = _default_sources()
        _save_sources(records)
        return records

    created_at_fallback = datetime.now().isoformat()
    records = [record for record in (_migrate_record(item, created_at_fallback) for item in raw) if record is not None]
    if not records:
        records = _default_sources()
        _save_sources(records)
        return records

    existing_ids = {record.id for record in records}
    for default in _default_sources():
        if default.id not in existing_ids:
            records.append(default)

    _save_sources(records)
    return records


def _save_sources(records: list[CalendarSourceRecord]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CALENDAR_SOURCES_PATH.write_text(
        json.dumps([record.model_dump() for record in records], indent=2) + "\n",
        encoding="utf-8",
    )


def validate_calendar_url(url: str) -> bool:
    trimmed = (url or "").strip()
    parsed = urlparse(trimmed)
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and ".ics" in trimmed.lower()
    )


def list_calendar_sources() -> list[CalendarSourceRecord]:
    return _load_sources()


def get_calendar_source(source_id: str) -> CalendarSourceRecord | None:
    for record in _load_sources():
        if record.id == source_id:
            return record
    return None


def create_calendar_source(payload: CalendarSourceCreate) -> CalendarSourceRecord:
    records = _load_sources()
    base_id = _normalize_id(payload.name)
    candidate_id = base_id
    suffix = 2
    existing_ids = {record.id for record in records}
    while candidate_id in existing_ids:
        candidate_id = f"{base_id}_{suffix}"
        suffix += 1

    now = datetime.now().isoformat()
    record = CalendarSourceRecord(
        id=candidate_id,
        name=payload.name.strip(),
        type=_normalized_type(payload.type),
        url=payload.url.strip(),
        enabled=payload.enabled,
        created_at=now,
        updated_at=now,
    )
    records.append(record)
    _save_sources(records)
    return record


def update_calendar_source(source_id: str, payload: CalendarSourceUpdate) -> CalendarSourceRecord | None:
    records = _load_sources()
    for index, record in enumerate(records):
        if record.id != source_id:
            continue

        updated = record.model_copy(
            update={
                "name": payload.name.strip() if isinstance(payload.name, str) else record.name,
                "type": _normalized_type(payload.type) if isinstance(payload.type, str) else record.type,
                "url": payload.url.strip() if isinstance(payload.url, str) else record.url,
                "enabled": payload.enabled if isinstance(payload.enabled, bool) else record.enabled,
                "updated_at": datetime.now().isoformat(),
            }
        )
        records[index] = updated
        _save_sources(records)
        return updated
    return None


def delete_calendar_source(source_id: str) -> bool:
    records = _load_sources()
    updated = [record for record in records if record.id != source_id]
    if len(updated) == len(records):
        return False
    _save_sources(updated)
    return True
