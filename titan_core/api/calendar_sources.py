from __future__ import annotations

from fastapi import APIRouter, HTTPException

from titan_core.calendar_store import (
    create_calendar_source,
    delete_calendar_source,
    get_calendar_source,
    list_calendar_sources,
    update_calendar_source,
    validate_calendar_url,
)
from titan_core.schemas import CalendarSourceCreate, CalendarSourceRecord, CalendarSourceUpdate


router = APIRouter()


@router.get("/calendar-sources", response_model=list[CalendarSourceRecord])
def get_calendar_sources() -> list[CalendarSourceRecord]:
    return list_calendar_sources()


@router.post("/calendar-sources", response_model=CalendarSourceRecord)
def add_calendar_source(payload: CalendarSourceCreate) -> CalendarSourceRecord:
    name = payload.name.strip()
    source_type = payload.type.strip().lower()
    url = payload.url.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Calendar source name is required.")
    if source_type not in {"canvas", "outlook", "other"}:
        raise HTTPException(status_code=400, detail="Invalid calendar type.")
    if url and not validate_calendar_url(url):
        raise HTTPException(status_code=400, detail="Invalid calendar URL.")
    if payload.enabled and not validate_calendar_url(url):
        raise HTTPException(status_code=400, detail="Invalid calendar URL.")
    return create_calendar_source(CalendarSourceCreate(name=name, type=source_type, url=url, enabled=payload.enabled))


@router.patch("/calendar-sources/{source_id}", response_model=CalendarSourceRecord)
def patch_calendar_source(source_id: str, payload: CalendarSourceUpdate) -> CalendarSourceRecord:
    existing = get_calendar_source(source_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Calendar source not found.")

    if isinstance(payload.type, str) and payload.type.strip().lower() not in {"canvas", "outlook", "other"}:
        raise HTTPException(status_code=400, detail="Invalid calendar type.")
    if isinstance(payload.url, str) and payload.url.strip() and not validate_calendar_url(payload.url.strip()):
        raise HTTPException(status_code=400, detail="Invalid calendar URL.")
    effective_url = payload.url.strip() if isinstance(payload.url, str) else existing.url
    if payload.enabled is True and not validate_calendar_url(effective_url):
        raise HTTPException(status_code=400, detail="Invalid calendar URL.")

    updated = update_calendar_source(source_id, payload)
    return updated


@router.delete("/calendar-sources/{source_id}")
def remove_calendar_source(source_id: str) -> dict:
    removed = delete_calendar_source(source_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Calendar source not found.")
    return {"status": "ok", "deleted": source_id}
