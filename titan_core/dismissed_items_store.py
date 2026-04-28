from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from titan_core.planning import PlannerItem
from titan_core.schemas import DismissedItemCreate, DismissedItemRecord


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DISMISSED_ITEMS_PATH = DATA_DIR / "dismissed_items.json"


def _ensure_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DISMISSED_ITEMS_PATH.exists():
        DISMISSED_ITEMS_PATH.write_text("[]\n", encoding="utf-8")


def _normalize(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _load_dismissed_items() -> list[DismissedItemRecord]:
    _ensure_store()
    raw = json.loads(DISMISSED_ITEMS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []

    items: list[DismissedItemRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            items.append(DismissedItemRecord(**item))
        except Exception:
            continue
    return items


def _save_dismissed_items(items: list[DismissedItemRecord]) -> None:
    _ensure_store()
    DISMISSED_ITEMS_PATH.write_text(
        json.dumps([item.model_dump() for item in items], indent=2) + "\n",
        encoding="utf-8",
    )


def stable_item_id(
    *,
    title: str | None,
    course: str | None,
    due_at: str | None,
    starts_at: str | None,
    source: str | None,
) -> str:
    stable_parts = [
        _normalize(title),
        _normalize(course),
        _normalize(due_at or starts_at),
        _normalize(source),
    ]
    digest = hashlib.sha1("|".join(stable_parts).encode("utf-8")).hexdigest()
    return digest[:16]


def stable_item_id_for_planner_item(item: PlannerItem) -> str:
    due_at = item.due_at.isoformat() if item.due_at else None
    starts_at = item.starts_at.isoformat() if item.starts_at else None
    return stable_item_id(
        title=item.title,
        course=item.course_name,
        due_at=due_at,
        starts_at=starts_at,
        source=item.source,
    )


def list_dismissed_items() -> list[DismissedItemRecord]:
    return _load_dismissed_items()


def dismissed_item_ids() -> set[str]:
    return {item.item_id for item in _load_dismissed_items()}


def dismiss_item(payload: DismissedItemCreate) -> DismissedItemRecord:
    items = _load_dismissed_items()
    existing = next((item for item in items if item.item_id == payload.item_id), None)
    now = datetime.now().isoformat()

    if existing is not None:
        updated = existing.model_copy(
            update={
                "title": payload.title.strip() or existing.title,
                "course": payload.course.strip() or existing.course,
                "dismissed_at": now,
                "reason": payload.reason.strip() or existing.reason,
            }
        )
        items = [updated if item.item_id == payload.item_id else item for item in items]
        _save_dismissed_items(items)
        return updated

    record = DismissedItemRecord(
        item_id=payload.item_id,
        title=payload.title.strip(),
        course=payload.course.strip(),
        dismissed_at=now,
        reason=payload.reason.strip() or "user dismissed",
    )
    items.append(record)
    _save_dismissed_items(items)
    return record
