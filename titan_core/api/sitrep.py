from __future__ import annotations

from datetime import datetime
import re

from fastapi import APIRouter, Query

from titan_core.canvas_feed import import_canvas_ics_from_url
from titan_core.config import settings
from titan_core.outlook_feed import import_outlook_ics_from_url
from titan_core.planning import PlannerItem
from titan_core.sitrep import build_sitrep
from titan_core.task_store import tasks_as_planner_items
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


def _spoken_clean(value: str | None) -> str:
    if not value:
        return "No data available."

    text = str(value)
    text = re.sub(r"https?://\S+", "", text)
    text = text.replace("\\n", " ").replace("\n", " ").replace("\\,", ",")
    text = re.sub(r"\s+", " ", text).strip(" .,:;|-")
    return text or "No data available."


def _spoken_when(value: str | None) -> str:
    if not value:
        return "No data available."
    try:
        dt = datetime.fromisoformat(value)
        time_part = dt.strftime("%I:%M %p").lstrip("0").replace(":00 ", " ")
        return f"{dt.strftime('%A')} at {time_part}"
    except ValueError:
        return _spoken_clean(value)


def _spoken_title(item: dict) -> str:
    title = _spoken_clean(item.get("title"))
    match = re.match(r"^(.*?)\s*\[(.*?)\]\s*$", title)
    if match:
        title = _spoken_clean(match.group(1))
    return title


def _spoken_course(item: dict) -> str:
    return _spoken_clean(item.get("course_name"))


def _spoken_block_title(block: dict) -> str:
    raw_title = block.get("source_item_title") or block.get("title")
    title = _spoken_clean(raw_title)
    match = re.match(r"^(study:\s*)?(.*?)\s*\[(.*?)\]\s*$", title, flags=re.IGNORECASE)
    if match:
        prefix = match.group(1) or ""
        core = _spoken_clean(match.group(2))
        if prefix:
            return f"{prefix.strip()} {core}".strip()
        return core
    return title


def _spoken_priority(item: dict) -> str:
    priority = item.get("priority")
    if isinstance(priority, int) and priority > 0:
        return f"Priority {priority}."
    return ""


def _spoken_weather(weather: str | None) -> str:
    cleaned = _spoken_clean(weather)
    if cleaned == "No data available.":
        return cleaned

    if ":" in cleaned:
        location, rest = cleaned.split(":", 1)
        location = _spoken_clean(location).title()
        rest = _spoken_clean(rest)
        if rest != "No data available.":
            return f"{location}, {rest}"
    return cleaned


def _dedupe_items(items: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen: set[str] = set()
    for item in items:
        key = "|".join(
            [
                _spoken_title(item).lower(),
                _spoken_course(item).lower(),
                str(item.get("due_at") or item.get("starts_at") or "").lower(),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _count_phrase(count: int, singular: str, plural: str | None = None) -> str:
    noun = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {noun}"


def _spoken_text(data: dict) -> str:
    must_do = _dedupe_items(data.get("must_do_today", []))
    blocks = data.get("suggested_blocks", [])
    still_open = _dedupe_items(data.get("still_open", []))
    today = _dedupe_items(data.get("today", []))
    weather = _spoken_weather(data.get("weather_summary"))
    lines = [
        "Good morning.",
        "Here is your briefing.",
        f"You have {_count_phrase(len(today), 'scheduled item')} today.",
    ]

    if must_do:
        top_item = must_do[0]
        title = _spoken_title(top_item)
        course = _spoken_course(top_item)
        due = _spoken_when(top_item.get("due_at") or top_item.get("starts_at"))
        lines.append("Top priority.")
        lines.append(title + ".")
        lines.append(f"For {course}.")
        lines.append(f"Due {due}.")
        priority_line = _spoken_priority(top_item)
        if priority_line:
            lines.append(priority_line)
    else:
        lines.append("Top priority. No data available.")

    if blocks:
        block = blocks[0]
        title = _spoken_block_title(block)
        start = _spoken_when(block.get("starts_at"))
        lines.append("Your next recommended study block.")
        lines.append(f"{title}, starting {start}.")
    else:
        lines.append("Your next recommended study block. No data available.")

    lines.append(f"Open tasks needing attention: {_count_phrase(len(still_open), 'task')}.")
    lines.append(f"Weather: {weather}.")
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

    task_items = tasks_as_planner_items()
    all_items.extend(task_items)
    source_counts["titan_tasks"] = len(task_items)

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
