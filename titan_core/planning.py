from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


ItemKind = Literal["calendar_event", "assignment", "test", "study_block", "reminder"]


@dataclass(slots=True)
class PlannerItem:
    title: str
    kind: ItemKind
    starts_at: datetime | None = None
    due_at: datetime | None = None
    source: str = "unknown"
    details: str = ""
    course_name: str | None = None
    estimated_minutes: int | None = None
    priority: int = 0
    is_complete: bool = False


@dataclass(slots=True)
class StudyBlockSuggestion:
    title: str
    starts_at: datetime
    ends_at: datetime
    reason: str
    source_item_title: str | None = None


@dataclass(slots=True)
class Sitrep:
    generated_at: datetime
    today_items: list[PlannerItem] = field(default_factory=list)
    must_do_today: list[PlannerItem] = field(default_factory=list)
    still_open: list[PlannerItem] = field(default_factory=list)
    suggested_blocks: list[StudyBlockSuggestion] = field(default_factory=list)
    weather_summary: str | None = None
