from __future__ import annotations

from datetime import date, datetime, time, timedelta
from math import ceil

from titan_core.planning import PlannerItem, Sitrep, StudyBlockSuggestion


def _norm(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def items_for_day(items: list[PlannerItem], target_day: date) -> list[PlannerItem]:
    results: list[PlannerItem] = []
    for item in items:
        when = _norm(item.starts_at) or _norm(item.due_at)
        if when and when.date() == target_day:
            results.append(item)
    return sorted(results, key=lambda x: _norm(x.starts_at) or _norm(x.due_at) or datetime.min)


def open_items(items: list[PlannerItem], now: datetime) -> list[PlannerItem]:
    now = _norm(now) or now
    results: list[PlannerItem] = []
    for item in items:
        if item.is_complete:
            continue
        due = _norm(item.due_at) or _norm(item.starts_at)
        if item.kind in {"assignment", "test", "reminder"} and (due is None or due >= now - timedelta(days=1)):
            results.append(item)
    return sorted(results, key=lambda x: _norm(x.due_at) or _norm(x.starts_at) or datetime.max)


def must_do_today(items: list[PlannerItem], target_day: date) -> list[PlannerItem]:
    today_open = []
    for item in items:
        if item.is_complete:
            continue
        due = _norm(item.due_at) or _norm(item.starts_at)
        if due and due.date() <= target_day and item.kind in {"assignment", "test", "reminder"}:
            today_open.append(item)
    return sorted(today_open, key=lambda x: _norm(x.due_at) or _norm(x.starts_at) or datetime.max)


def _busy_windows(items: list[PlannerItem], start_day: date, num_days: int = 8) -> dict[date, list[tuple[datetime, datetime]]]:
    windows: dict[date, list[tuple[datetime, datetime]]] = {}
    valid_days = {start_day + timedelta(days=i) for i in range(num_days)}
    for item in items:
        if item.kind != "calendar_event":
            continue
        start = _norm(item.starts_at)
        end = _norm(item.due_at) or start
        if not start or not end:
            continue
        if start.date() not in valid_days:
            continue
        windows.setdefault(start.date(), []).append((start, end))
    for day in windows:
        windows[day].sort(key=lambda pair: pair[0])
    return windows


def _overlaps(start: datetime, end: datetime, windows: list[tuple[datetime, datetime]]) -> bool:
    for busy_start, busy_end in windows:
        if start < busy_end and end > busy_start:
            return True
    return False


def _estimate_minutes(item: PlannerItem, block_minutes: int) -> int:
    if item.estimated_minutes:
        return item.estimated_minutes
    title = item.title.lower()
    if item.kind == "test":
        return max(90, block_minutes * 3)
    if any(word in title for word in ("project", "paper", "essay", "presentation", "final")):
        return max(120, block_minutes * 4)
    return max(block_minutes, 60)


def _reason_for(item: PlannerItem, session_index: int, total_sessions: int) -> str:
    if item.kind == "test":
        if session_index == total_sessions - 1:
            return "Final review before the test"
        return "Practice and review before the test"
    if total_sessions > 1 and session_index == 0:
        return "Start early and avoid rushing"
    if total_sessions > 1 and session_index == total_sessions - 1:
        return "Finish with buffer before the deadline"
    return "Keep steady progress before the deadline"


def suggest_study_blocks(items: list[PlannerItem], now: datetime, block_minutes: int = 30) -> list[StudyBlockSuggestion]:
    now = _norm(now) or now
    busy_by_day = _busy_windows(items, now.date(), num_days=8)
    scheduled_by_day: dict[date, list[tuple[datetime, datetime]]] = {day: list(windows) for day, windows in busy_by_day.items()}
    suggestions: list[StudyBlockSuggestion] = []

    candidates = [item for item in open_items(items, now) if item.kind in {"assignment", "test"}]

    for item in candidates[:8]:
        due = _norm(item.due_at) or _norm(item.starts_at) or (now + timedelta(days=3))
        latest_finish = due - (timedelta(hours=12) if item.kind == "test" else timedelta(days=1))
        if latest_finish < now:
            latest_finish = due
        earliest_start = min(now, latest_finish)
        lookahead_start = max(now, due - timedelta(days=7))
        if lookahead_start > earliest_start:
            earliest_start = lookahead_start

        total_minutes = _estimate_minutes(item, block_minutes)
        total_sessions = max(1, min(ceil(total_minutes / block_minutes), 6 if item.kind == "assignment" else 5))
        placed = 0
        day_cursor = now.date()
        end_day = latest_finish.date()

        while day_cursor <= end_day and placed < total_sessions:
            day_windows = scheduled_by_day.setdefault(day_cursor, [])
            day_start = datetime.combine(day_cursor, time(6, 0))
            day_end = datetime.combine(day_cursor, time(22, 0))
            if day_cursor == now.date() and now > day_start:
                day_start = (now + timedelta(minutes=(30 - now.minute % 30) % 30)).replace(second=0, microsecond=0)

            slot = day_start
            while slot + timedelta(minutes=block_minutes) <= day_end and placed < total_sessions:
                slot_end = slot + timedelta(minutes=block_minutes)
                if slot_end > latest_finish:
                    break
                if not _overlaps(slot, slot_end, day_windows):
                    suggestion = StudyBlockSuggestion(
                        title=f"Study: {item.title}",
                        starts_at=slot,
                        ends_at=slot_end,
                        reason=_reason_for(item, placed, total_sessions),
                        source_item_title=item.title,
                    )
                    suggestions.append(suggestion)
                    day_windows.append((slot, slot_end))
                    day_windows.sort(key=lambda pair: pair[0])
                    placed += 1
                    slot += timedelta(minutes=block_minutes)
                    if item.kind == "assignment":
                        break
                slot += timedelta(minutes=30)
            day_cursor += timedelta(days=1)

    suggestions.sort(key=lambda s: s.starts_at)
    return suggestions[:12]


def build_sitrep(all_items: list[PlannerItem], now: datetime, weather_summary: str | None = None, block_minutes: int = 30) -> Sitrep:
    now = _norm(now) or now
    today = now.date()
    return Sitrep(
        generated_at=now,
        today_items=items_for_day(all_items, today),
        must_do_today=must_do_today(all_items, today),
        still_open=open_items(all_items, now),
        suggested_blocks=suggest_study_blocks(all_items, now, block_minutes=block_minutes),
        weather_summary=weather_summary,
    )
