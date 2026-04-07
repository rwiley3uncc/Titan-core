from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from titan_core.planning import PlannerItem, Sitrep, StudyBlockSuggestion


def items_for_day(items: list[PlannerItem], target_day: date) -> list[PlannerItem]:
    results: list[PlannerItem] = []
    for item in items:
        when = item.starts_at or item.due_at
        if when and when.date() == target_day:
            results.append(item)
    return sorted(results, key=lambda x: x.starts_at or x.due_at or datetime.min)


def open_items(items: list[PlannerItem], now: datetime) -> list[PlannerItem]:
    results: list[PlannerItem] = []
    for item in items:
        if item.is_complete:
            continue
        if item.kind in {"assignment", "test", "reminder"}:
            results.append(item)
    return sorted(results, key=lambda x: x.due_at or datetime.max)


def must_do_today(items: list[PlannerItem], target_day: date) -> list[PlannerItem]:
    today_open = []
    for item in items:
        if item.is_complete:
            continue
        due = item.due_at or item.starts_at
        if due and due.date() <= target_day and item.kind in {"assignment", "test", "reminder"}:
            today_open.append(item)
    return sorted(today_open, key=lambda x: x.due_at or x.starts_at or datetime.max)


def suggest_study_blocks(
    items: list[PlannerItem],
    now: datetime,
    block_minutes: int = 30,
) -> list[StudyBlockSuggestion]:
    suggestions: list[StudyBlockSuggestion] = []
    candidate_items = [
        item for item in open_items(items, now)
        if item.kind in {"assignment", "test"}
    ]

    start_anchor = now.replace(second=0, microsecond=0)
    if start_anchor.minute not in {0, 30}:
        start_anchor = start_anchor.replace(minute=30 if start_anchor.minute < 30 else 0)
        if start_anchor.minute == 0:
            start_anchor += timedelta(hours=1)

    for idx, item in enumerate(candidate_items[:3]):
        starts_at = start_anchor + timedelta(minutes=block_minutes * idx)
        ends_at = starts_at + timedelta(minutes=block_minutes)
        reason = "Start early and avoid rushing" if item.kind == "assignment" else "Practice/review before the test"
        suggestions.append(
            StudyBlockSuggestion(
                title=f"Study: {item.title}",
                starts_at=starts_at,
                ends_at=ends_at,
                reason=reason,
                source_item_title=item.title,
            )
        )

    return suggestions


def build_sitrep(
    all_items: list[PlannerItem],
    now: datetime,
    weather_summary: str | None = None,
    block_minutes: int = 30,
) -> Sitrep:
    today = now.date()
    return Sitrep(
        generated_at=now,
        today_items=items_for_day(all_items, today),
        must_do_today=must_do_today(all_items, today),
        still_open=open_items(all_items, now),
        suggested_blocks=suggest_study_blocks(all_items, now, block_minutes=block_minutes),
        weather_summary=weather_summary,
    )
