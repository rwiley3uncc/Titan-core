from __future__ import annotations

from datetime import datetime, timedelta
import re

from fastapi import APIRouter, HTTPException, Query

from titan_core.canvas_feed import import_canvas_ics_from_url
from titan_core.calendar_store import list_calendar_sources
from titan_core.config import settings
from titan_core.dismissed_items_store import (
    dismiss_item,
    dismissed_item_ids,
    list_dismissed_items,
    stable_item_id_for_planner_item,
)
from titan_core.outlook_feed import import_outlook_ics_from_url
from titan_core.planning import PlannerItem
from titan_core.schemas import DismissedItemCreate, DismissedItemRecord
from titan_core.sitrep import build_sitrep
from titan_core.task_store import tasks_as_planner_items
from titan_core.weather import fetch_weather_summary

router = APIRouter()


def _serialize_item(item: PlannerItem) -> dict:
    item_id = stable_item_id_for_planner_item(item)
    return {
        "item_id": item_id,
        "title": item.title,
        "kind": item.kind,
        "starts_at": item.starts_at.isoformat() if item.starts_at else None,
        "due_at": item.due_at.isoformat() if item.due_at else None,
        "source": item.source,
        "details": item.details,
        "location": item.location,
        "course_name": item.course_name,
        "estimated_minutes": item.estimated_minutes,
        "priority": item.priority,
        "is_complete": item.is_complete,
    }


def _with_source(items: list[PlannerItem], source_name: str) -> list[PlannerItem]:
    return [
        PlannerItem(
            title=item.title,
            kind=item.kind,
            starts_at=item.starts_at,
            due_at=item.due_at,
            source=source_name,
            details=item.details,
            location=item.location,
            course_name=item.course_name,
            estimated_minutes=item.estimated_minutes,
            priority=item.priority,
            is_complete=item.is_complete,
        )
        for item in items
    ]


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


def _spoken_time(value: str | None) -> str:
    if not value:
        return "No data available."
    try:
        return datetime.fromisoformat(value).strftime("%I:%M %p").lstrip("0").replace(":00 ", " ")
    except ValueError:
        return _spoken_clean(value)


def _spoken_title(item: dict) -> str:
    title = _spoken_clean(item.get("title"))
    match = re.match(r"^(.*?)\s*\[(.*?)\]\s*$", title)
    if match:
        title = _spoken_clean(match.group(1))
    return title


def _extract_course_code(text: str | None) -> str | None:
    cleaned = _spoken_clean(text)
    if cleaned == "No data available.":
        return None

    match = re.search(r"([A-Z]{2,5}-\d{3,5}[A-Z]?)", cleaned)
    if match:
        return match.group(1)

    return None


def _spoken_course(item: dict) -> str:
    title = _spoken_clean(item.get("title"))
    bracket_match = re.search(r"\[(.*?)\]\s*$", title)
    if bracket_match:
        extracted = _extract_course_code(bracket_match.group(1))
        if extracted:
            return extracted

    extracted = _extract_course_code(item.get("course_name"))
    if extracted:
        return extracted

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


def _spoken_location(location: str | None) -> str | None:
    cleaned = _spoken_clean(location)
    if cleaned == "No data available.":
        return None

    match = re.match(r"^(.*?)[,\s]+([A-Za-z]?\d{2,4}[A-Za-z]?)$", cleaned)
    if match:
        building = _spoken_clean(match.group(1))
        room = _spoken_clean(match.group(2))
        if building != "No data available." and room != "No data available.":
            return f"In {building}, room {room}."

    return f"In {cleaned}."


def _next_class_item(items: list[PlannerItem], now: datetime) -> PlannerItem | None:
    today = now.date()
    candidates = [
        item
        for item in items
        if item.kind == "calendar_event"
        and item.starts_at is not None
        and item.starts_at.date() == today
        and item.starts_at > now
    ]
    candidates.sort(key=lambda item: item.starts_at or datetime.max)
    return candidates[0] if candidates else None


def _next_class_payload(item: PlannerItem | None) -> dict | None:
    if item is None:
        return None

    serialized = _serialize_item(item)
    return {
        "title": _spoken_title(serialized),
        "course_code": _spoken_course(serialized),
        "starts_at": serialized.get("starts_at"),
        "location": _spoken_clean(serialized.get("location")) if serialized.get("location") else None,
    }


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


def _filter_dismissed_overdue(items: list[PlannerItem], now: datetime, dismissed_ids: set[str]) -> list[PlannerItem]:
    filtered: list[PlannerItem] = []
    for item in items:
        due = _assignment_due_value(item)
        if (
            item.kind in {"assignment", "test", "reminder"}
            and due is not None
            and due < now
            and stable_item_id_for_planner_item(item) in dismissed_ids
        ):
            continue
        filtered.append(item)
    return filtered


def _assignment_due_value(item: PlannerItem) -> datetime | None:
    return item.due_at or item.starts_at


def _classify_assignment_items(items: list[PlannerItem], now: datetime) -> dict[str, list[PlannerItem]]:
    buckets: dict[str, list[PlannerItem]] = {
        "overdue": [],
        "due_today": [],
        "due_tomorrow": [],
        "due_this_week": [],
        "future": [],
    }

    for item in items:
        if item.is_complete:
            continue
        if item.kind not in {"assignment", "test", "reminder"}:
            continue
        due = _assignment_due_value(item)
        if due is None:
            continue

        if due < now:
            buckets["overdue"].append(item)
        elif due.date() == now.date():
            buckets["due_today"].append(item)
        elif due.date() == (now + timedelta(days=1)).date():
            buckets["due_tomorrow"].append(item)
        elif due <= now + timedelta(days=7):
            buckets["due_this_week"].append(item)
        else:
            buckets["future"].append(item)

    for bucket_items in buckets.values():
        bucket_items.sort(key=lambda item: _assignment_due_value(item) or datetime.max)

    return buckets


def _serialized_assignments(items: list[PlannerItem]) -> list[dict]:
    return [_serialize_item(item) for item in items]


def _with_overdue_flag(items: list[dict], overdue_ids: set[str]) -> list[dict]:
    annotated: list[dict] = []
    for item in items:
        enriched = dict(item)
        enriched["is_overdue"] = item.get("item_id") in overdue_ids
        annotated.append(enriched)
    return annotated


def _spoken_text(data: dict) -> str:
    must_do = _dedupe_items(data.get("must_do_today", []))
    blocks = data.get("suggested_blocks", [])
    still_open = _dedupe_items(data.get("still_open", []))
    today = _dedupe_items(data.get("today", []))
    next_class = data.get("next_class")
    due_today = data.get("due_today_assignments", [])
    due_tomorrow = data.get("due_tomorrow_assignments", [])
    due_this_week = data.get("due_this_week_assignments", [])
    top_priority_item = data.get("top_priority_item") or (must_do[0] if must_do else None)
    weather = _spoken_weather(data.get("weather_summary"))
    due_this_week_count = len(due_today) + len(due_tomorrow) + len(due_this_week)
    lines = [
        "Good morning.",
        "Here is your briefing.",
        f"You have {_count_phrase(len(today), 'scheduled item')} today.",
    ]

    if next_class:
        class_course = _spoken_clean(next_class.get("course_code"))
        class_start = _spoken_time(next_class.get("starts_at"))
        class_location = _spoken_location(next_class.get("location")) if next_class.get("location") else None
        class_subject = class_course if class_course != "No data available." else _spoken_clean(next_class.get("title"))
        lines.append(f"Your next class is {class_subject}, starting at {class_start}.")
        if class_location:
            lines.append(class_location)
    else:
        lines.append("No upcoming classes today.")

    lines.append(f"You have {_count_phrase(due_this_week_count, 'assignment')} due this week.")

    if top_priority_item:
        top_item = top_priority_item
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
    dismissed_ids = dismissed_item_ids()

    task_items = tasks_as_planner_items()
    all_items.extend(task_items)
    source_counts["titan_tasks"] = len(task_items)

    enabled_saved_sources = [source for source in list_calendar_sources() if source.enabled]

    if not enabled_saved_sources:
        warnings.append("No calendar sources configured.")

    for calendar_source in enabled_saved_sources:
        if not calendar_source.enabled:
            continue
        try:
            if calendar_source.type == "outlook":
                result = import_outlook_ics_from_url(calendar_source.url)
            else:
                result = import_canvas_ics_from_url(calendar_source.url)
            sourced_items = _with_source(result.items, f"calendar_source:{calendar_source.id}")
            all_items.extend(sourced_items)
            source_counts[f"calendar_source:{calendar_source.id}"] = len(sourced_items)
        except Exception as exc:
            warnings.append(f"{calendar_source.name} feed import failed: {exc}")

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

    filtered_items = _filter_dismissed_overdue(all_items, now, dismissed_ids)
    sitrep = build_sitrep(filtered_items, now=now, weather_summary=weather_summary, block_minutes=settings.study_block_minutes)
    next_class = _next_class_payload(_next_class_item(all_items, now))
    assignment_buckets = _classify_assignment_items(filtered_items, now)
    overdue_ids = {stable_item_id_for_planner_item(item) for item in assignment_buckets["overdue"]}
    top_priority_source = (
        assignment_buckets["due_today"]
        or assignment_buckets["due_tomorrow"]
        or assignment_buckets["due_this_week"]
        or assignment_buckets["overdue"]
    )
    top_priority_item = _serialize_item(top_priority_source[0]) if top_priority_source else None
    upcoming_assignments = _serialized_assignments(
        (assignment_buckets["due_tomorrow"] + assignment_buckets["due_this_week"])[:3]
    )
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
        "today": _with_overdue_flag([_serialize_item(item) for item in sitrep.today_items], overdue_ids),
        "must_do_today": _with_overdue_flag([_serialize_item(item) for item in sitrep.must_do_today], overdue_ids),
        "still_open": _with_overdue_flag([_serialize_item(item) for item in sitrep.still_open[:15]], overdue_ids),
        "overdue_assignments": _serialized_assignments(assignment_buckets["overdue"]),
        "due_today_assignments": _serialized_assignments(assignment_buckets["due_today"]),
        "due_tomorrow_assignments": _serialized_assignments(assignment_buckets["due_tomorrow"]),
        "due_this_week_assignments": _serialized_assignments(assignment_buckets["due_this_week"]),
        "future_assignments": _serialized_assignments(assignment_buckets["future"]),
        "top_priority_item": top_priority_item,
        "upcoming_assignments": upcoming_assignments,
        "next_class": next_class,
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


@router.get("/dismissed-items", response_model=list[DismissedItemRecord])
def get_dismissed_items() -> list[DismissedItemRecord]:
    return list_dismissed_items()


@router.post("/dismissed-items", response_model=DismissedItemRecord)
def post_dismissed_item(payload: DismissedItemCreate) -> DismissedItemRecord:
    item_id = payload.item_id.strip()
    title = payload.title.strip()
    course = payload.course.strip()
    if not item_id or not title:
        raise HTTPException(status_code=400, detail="Dismissed item id and title are required.")
    if len(item_id) < 8:
        raise HTTPException(status_code=400, detail="Invalid dismissed item id.")

    return dismiss_item(
        DismissedItemCreate(
            item_id=item_id,
            title=title,
            course=course or "No data available.",
            reason=payload.reason or "user dismissed",
        )
    )
