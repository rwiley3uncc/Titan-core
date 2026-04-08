from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.request import urlopen
import re

from titan_core.planning import PlannerItem


@dataclass(slots=True)
class CanvasFeedImportResult:
    items: list[PlannerItem]
    raw_event_count: int


def _parse_dt(value: str) -> datetime | None:
    value = value.strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if fmt.endswith("Z"):
                return dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            continue
    return None


def _extract_course_name(summary: str) -> str | None:
    match = re.search(r"\[(.*?)\]", summary)
    return match.group(1).strip() if match else None


def _kind_from_summary(summary: str) -> str:
    lowered = summary.lower()
    if "test" in lowered or "exam" in lowered or "quiz" in lowered:
        return "test"
    if "assignment" in lowered or "due" in lowered or "discussion" in lowered:
        return "assignment"
    return "calendar_event"


def parse_canvas_ics_text(text: str) -> CanvasFeedImportResult:
    items: list[PlannerItem] = []
    current: dict[str, str] = {}
    in_event = False
    raw_event_count = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line == "BEGIN:VEVENT":
            current = {}
            in_event = True
            raw_event_count += 1
            continue
        if line == "END:VEVENT":
            if current:
                summary = current.get("SUMMARY", "Untitled item")
                starts_at = _parse_dt(current.get("DTSTART", ""))
                due_at = _parse_dt(current.get("DTEND", "")) or starts_at
                items.append(PlannerItem(title=summary, kind=_kind_from_summary(summary), starts_at=starts_at, due_at=due_at, source="canvas_ics", details=current.get("DESCRIPTION", ""), course_name=_extract_course_name(summary)))
            current = {}
            in_event = False
            continue
        if not in_event or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.split(";", 1)[0]
        current[key] = value

    return CanvasFeedImportResult(items=items, raw_event_count=raw_event_count)


def import_canvas_ics_from_url(feed_url: str) -> CanvasFeedImportResult:
    with urlopen(feed_url, timeout=15) as response:  # nosec B310
        text = response.read().decode("utf-8", errors="replace")
    return parse_canvas_ics_text(text)
