from __future__ import annotations

import json
import os
from dataclasses import dataclass

# --------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# --------------------------------------------------

from dotenv import load_dotenv
load_dotenv()


# --------------------------------------------------
# SETTINGS CLASS
# --------------------------------------------------

@dataclass(slots=True)
class TitanSettings:
    owner_username: str = os.getenv("TITAN_OWNER_USERNAME", "ron")

    sitrep_time: str = os.getenv(
        "TITAN_SITREP_TIME",
        "08:00"
    )

    study_block_minutes: int = int(
        os.getenv(
            "TITAN_STUDY_BLOCK_MINUTES",
            "30"
        )
    )

    canvas_ics_url: str | None = (
        os.getenv("TITAN_CANVAS_ICS_URL") or None
    )

    outlook_calendar_email: str | None = (
        os.getenv("TITAN_OUTLOOK_CALENDAR_EMAIL") or None
    )

    outlook_ics_url: str | None = (
        os.getenv("TITAN_OUTLOOK_ICS_URL") or None
    )

    calendar_sources_json: str | None = (
        os.getenv("TITAN_CALENDAR_SOURCES_JSON") or None
    )

    def configured_calendar_sources(self) -> list[dict[str, object]]:
        raw = (self.calendar_sources_json or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []

        normalized: list[dict[str, object]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "Calendar").strip()
            source_type = str(item.get("type") or "other").strip().lower()
            url = str(item.get("url") or "").strip()
            enabled = bool(item.get("enabled", True))
            if not url:
                continue
            normalized.append(
                {
                    "name": name or "Calendar",
                    "type": source_type,
                    "url": url,
                    "enabled": enabled,
                }
            )
        return normalized


# --------------------------------------------------
# GLOBAL SETTINGS INSTANCE
# --------------------------------------------------

settings = TitanSettings()
