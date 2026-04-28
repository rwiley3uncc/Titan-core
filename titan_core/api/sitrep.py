from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query

from titan_core.canvas_feed import import_canvas_ics_from_url
from titan_core.config import settings
from titan_core.outlook_feed import import_outlook_ics_from_url
from titan_core.planning import PlannerItem
from titan_core.sitrep import build_sitrep
from titan_core.weather import fetch_weather_summary

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


def _spoken_text(data: dict) -> str:
    must_do = data.get("must_do_today", [])
    blocks = data.get("suggested_blocks", [])
    still_open = data.get("still_open", [])
    today = data.get("today", [])
    weather = data.get("weather_summary")
    lines = [
        "Good morning. Here's your briefing for today.",
        f"Today at a glance: {len(today)} scheduled items, {len(must_do)} tasks needing attention, and {len(still_open)} still-open school tasks.",
    ]

    if must_do:
        top_item = must_do[0]
        title = top_item.get("title") or "No data available."
        course = top_item.get("course_name") or "No data available."
        due = top_item.get("due_at") or top_item.get("starts_at") or "No data available."
        lines.append(f"Top priority: {title}. Course: {course}. Due: {due}.")
    else:
        lines.append("Top priority: No data available.")

    if blocks:
        block = blocks[0]
        title = block.get("title") or "No data available."
        start = block.get("starts_at") or "No data available."
        lines.append(f"Recommended next step: {title}. Start: {start}.")
    else:
        lines.append("Recommended next step: No data available.")

    lines.append(f"Weather: {weather or 'No data available.'}")
    return " ".join(lines)


def build_sitrep_payload(
    weather_summary: str | None = None,
    now_iso: str | None = None,
    weather_location: str | None = "Charlotte",
) -> dict:
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

    if settings.outlook_ics_url:
        try:
            outlook_result = import_outlook_ics_from_url(settings.outlook_ics_url)
            all_items.extend(outlook_result.items)
            source_counts["outlook_ics"] = len(outlook_result.items)
        except Exception as exc:
            warnings.append(f"Outlook ICS import failed: {exc}")
    elif settings.outlook_calendar_email:
        warnings.append("Outlook target account is set, but TITAN_OUTLOOK_ICS_URL is missing.")
    else:
        warnings.append("Outlook calendar integration is not configured yet. Set TITAN_OUTLOOK_CALENDAR_EMAIL and TITAN_OUTLOOK_ICS_URL.")

    if weather_summary is None:
        try:
            weather_summary = fetch_weather_summary(weather_location or "Charlotte")
        except Exception as exc:
            warnings.append(f"Weather fetch failed: {exc}")
            weather_summary = None

    sitrep = build_sitrep(all_items, now=now, weather_summary=weather_summary, block_minutes=settings.study_block_minutes)
    payload = {
        "generated_at": sitrep.generated_at.isoformat(),
        "configuration": {
            "sitrep_time": settings.sitrep_time,
            "study_block_minutes": settings.study_block_minutes,
            "calendar_scope": "school_and_life",
            "scheduling_mode": "suggest_first",
            "outlook_calendar_email": settings.outlook_calendar_email,
            "canvas_feed_configured": bool(settings.canvas_ics_url),
            "outlook_feed_configured": bool(settings.outlook_ics_url),
        },
        "warnings": warnings,
        "source_counts": source_counts,
        "today": [_serialize_item(item) for item in sitrep.today_items],
        "must_do_today": [_serialize_item(item) for item in sitrep.must_do_today],
        "still_open": [_serialize_item(item) for item in sitrep.still_open[:15]],
        "suggested_blocks": [
            {
                "title": b.title,
                "starts_at": b.starts_at.isoformat(),
                "ends_at": b.ends_at.isoformat(),
                "reason": b.reason,
                "source_item_title": b.source_item_title,
            }
            for b in sitrep.suggested_blocks
        ],
        "weather_summary": sitrep.weather_summary,
    }
    payload["spoken_text"] = _spoken_text(payload)
    return payload


@router.get("/sitrep")
def get_sitrep(
    weather_summary: str | None = Query(default=None),
    now_iso: str | None = Query(default=None),
    weather_location: str | None = Query(default="Charlotte"),
):
    return build_sitrep_payload(
        weather_summary=weather_summary,
        now_iso=now_iso,
        weather_location=weather_location,
    )
