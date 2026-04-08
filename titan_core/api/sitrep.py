from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from titan_core.canvas_feed import import_canvas_ics_from_url
from titan_core.config import settings
from titan_core.planning import PlannerItem
from titan_core.sitrep import build_sitrep

router = APIRouter()


def _serialize_item(item: PlannerItem) -> dict:
    return {
        "title": item.title,
        "kind": item.kind,
        "starts_at": item.starts_at.isoformat() if item.starts_at else None,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "source": item.source,
        "details": item.details,
        "course_name": item.course_name,
        "estimated_minutes": item.estimated_minutes,
        "priority": item.priority,
        "is_complete": item.is_complete,
    }


@router.get("/sitrep")
def get_sitrep(weather_summary: str | None = Query(default=None), now_iso: str | None = Query(default=None)):
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now()
    warnings: list[str] = []
    all_items: list[PlannerItem] = []
    source_counts: dict[str, int] = {}

    if settings.canvas_ics_url:
        try:
            canvas_result = import_canvas_ics_from_url(settings.canvas_ics_url)
            all_items.extend(canvas_result.items)
            source_counts["canvas_ics"] = len(canvas_result.items)
        except Exception as exc:
            warnings.append(f"Canvas feed import failed: {exc}")
    else:
        warnings.append("Canvas ICS feed is not configured. Set TITAN_CANVAS_ICS_URL in your environment.")

    if not settings.outlook_calendar_email:
        warnings.append("Outlook calendar integration is not configured yet. Set TITAN_OUTLOOK_CALENDAR_EMAIL for the target account.")
    else:
        warnings.append("Live Outlook sync is not wired yet; this endpoint currently uses Canvas-derived items plus placeholders for life scheduling.")

    sitrep = build_sitrep(all_items, now=now, weather_summary=weather_summary, block_minutes=settings.study_block_minutes)
    return {
        "generated_at": sitrep.generated_at.isoformat(),
        "configuration": {
            "sitrep_time": settings.sitrep_time,
            "study_block_minutes": settings.study_block_minutes,
            "calendar_scope": "school_and_life",
            "scheduling_mode": "suggest_first",
            "outlook_calendar_email": settings.outlook_calendar_email,
            "canvas_feed_configured": bool(settings.canvas_ics_url),
        },
        "warnings": warnings,
        "source_counts": source_counts,
        "today": [_serialize_item(item) for item in sitrep.today_items],
        "must_do_today": [_serialize_item(item) for item in sitrep.must_do_today],
        "still_open": [_serialize_item(item) for item in sitrep.still_open[:15]],
        "suggested_blocks": [{"title": b.title, "starts_at": b.starts_at.isoformat(), "ends_at": b.ends_at.isoformat(), "reason": b.reason, "source_item_title": b.source_item_title} for b in sitrep.suggested_blocks],
        "weather_summary": sitrep.weather_summary,
    }
