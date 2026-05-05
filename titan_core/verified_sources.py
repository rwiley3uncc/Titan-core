from __future__ import annotations

from dataclasses import dataclass
from typing import Any


APPROVED_LOCAL_SOURCE_FOLDERS = ("docs",)
APPROVED_SOURCE_TYPES = {
    "sitrep_payload",
    "calendar_source_data",
    "uploaded_file",
    "local_verified_doc",
    "approved_registry_entry",
    "verified_web_result",
}
SOURCE_CONFIDENCE_LABELS = ("low", "medium", "high")

PERSONAL_VERIFIED_SOURCE_REQUIRED_REPLY = """I don't have a verified source for that topic yet.

You can:
- upload your course notes or textbook
- add an approved source
- enable verified web lookup

Then I can help using trusted information."""
PERSONAL_VERIFIED_WEB_REQUIRED_REPLY = """I don't have a verified current source for that yet.

You can:
- enable verified web lookup
- add an approved web source
- upload a trusted reference

Then I can answer from verified information."""

PERSONAL_GROUNDED_INTENTS = {
    "schedule_today",
    "must_do_today",
    "still_open",
    "study_next",
    "refresh_sitrep",
    "read_sitrep",
    "daily_plan",
    "daily_overview",
    "next_deadline",
}


@dataclass
class VerifiedSourceResult:
    names: list[str]
    context_texts: list[str]
    source_types: list[str]
    confidence: str
    status: str


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _looks_like_current_fact_request(message: str) -> bool:
    lowered = _normalize_text(message)
    hints = (
        "current ",
        "latest ",
        "most recent",
        "today",
        "ceo",
        "president",
        "price",
        "stock",
        "weather",
        "news",
    )
    return any(hint in lowered for hint in hints)


def is_current_fact_request(message: str) -> bool:
    return _looks_like_current_fact_request(message)


def _sitrep_source_context(payload: dict[str, Any]) -> str:
    generated_at = payload.get("generated_at") or "unknown time"
    today = payload.get("today", [])
    must_do = payload.get("must_do_today", [])
    still_open = payload.get("still_open", [])
    suggested_blocks = payload.get("suggested_blocks", [])
    return (
        f"Sitrep payload generated at {generated_at}. "
        f"Today's items: {len(today)}. Must-do items: {len(must_do)}. "
        f"Still-open items: {len(still_open)}. Suggested study blocks: {len(suggested_blocks)}."
    )


def get_verified_source_details(message: str, context: dict[str, Any]) -> VerifiedSourceResult:
    names: list[str] = []
    context_texts: list[str] = []
    source_types: list[str] = []

    personal_intent = context.get("personal_intent")
    sitrep_payload = context.get("sitrep_payload")
    if personal_intent in PERSONAL_GROUNDED_INTENTS and isinstance(sitrep_payload, dict):
        names.append("sitrep payload")
        source_types.append("sitrep_payload")
        context_texts.append(_sitrep_source_context(sitrep_payload))

        calendar_sources = sitrep_payload.get("source_counts") or {}
        if isinstance(calendar_sources, dict) and calendar_sources:
            names.append("calendar source data")
            source_types.append("calendar_source_data")

    file_name = str(context.get("file_name") or "").strip()
    file_content = context.get("file_content")
    if file_name and isinstance(file_content, str) and file_content.strip():
        names.append(file_name)
        source_types.append("uploaded_file")
        context_texts.append(
            f"Verified uploaded source: {file_name}\n"
            "Use only the following source text when answering:\n"
            f"{file_content}"
        )

    for doc in context.get("docs_sources", []) or []:
        if not isinstance(doc, dict):
            continue
        doc_name = str(doc.get("name") or "").strip()
        doc_content = str(doc.get("content") or "").strip()
        if not doc_name or not doc_content:
            continue
        names.append(doc_name)
        source_types.append("local_verified_doc")
        context_texts.append(
            f"Verified local document: {doc_name}\n"
            f"{doc_content}"
        )

    for entry in context.get("approved_registry_entries", []) or []:
        if not isinstance(entry, dict):
            continue
        entry_name = str(entry.get("name") or "").strip()
        entry_content = str(entry.get("content") or "").strip()
        if not entry_name or not entry_content:
            continue
        names.append(entry_name)
        source_types.append("approved_registry_entry")
        context_texts.append(
            f"Approved source registry entry: {entry_name}\n"
            f"{entry_content}"
        )

    verified_web = context.get("verified_web")
    if verified_web:
        web_sources = getattr(verified_web, "sources", []) or []
        source_lines: list[str] = []
        for source in web_sources:
            title = str(getattr(source, "title", "Verified web source")).strip()
            url = str(getattr(source, "url", "")).strip()
            snippet = str(getattr(source, "extracted_text", "")).strip()
            if not url or not snippet:
                continue
            names.append(title)
            source_types.append("verified_web_result")
            source_lines.append(
                f"- {title} ({url}): {snippet}"
            )
        if source_lines:
            context_texts.append(
                "Verified web sources:\n"
                + "\n".join(source_lines)
            )

    deduped_names: list[str] = []
    for name in names:
        if name not in deduped_names:
            deduped_names.append(name)

    confidence = "low"
    if "uploaded_file" in source_types or "sitrep_payload" in source_types:
        confidence = "high"
    elif "verified_web_result" in source_types:
        confidence = "medium"
    elif source_types:
        confidence = "medium"

    status = "verified" if deduped_names else "missing_verified_source"
    return VerifiedSourceResult(
        names=deduped_names,
        context_texts=context_texts,
        source_types=source_types,
        confidence=confidence,
        status=status,
    )


def has_verified_source_for_topic(message: str, context: dict[str, Any]) -> bool:
    return bool(get_verified_source_details(message, context).names)


def get_verified_source_context(message: str, context: dict[str, Any]) -> str | None:
    details = get_verified_source_details(message, context)
    if not details.context_texts:
        return None
    return "\n\n".join(details.context_texts)


def missing_verified_source_reply(message: str) -> str:
    if _looks_like_current_fact_request(message):
        return PERSONAL_VERIFIED_WEB_REQUIRED_REPLY
    return PERSONAL_VERIFIED_SOURCE_REQUIRED_REPLY
