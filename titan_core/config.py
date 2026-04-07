from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class TitanSettings:
    owner_username: str = os.getenv("TITAN_OWNER_USERNAME", "ron")
    sitrep_time: str = os.getenv("TITAN_SITREP_TIME", "08:00")
    study_block_minutes: int = int(os.getenv("TITAN_STUDY_BLOCK_MINUTES", "30"))
    canvas_ics_url: str | None = os.getenv("TITAN_CANVAS_ICS_URL") or None
    outlook_calendar_email: str | None = os.getenv("TITAN_OUTLOOK_CALENDAR_EMAIL") or None


settings = TitanSettings()
