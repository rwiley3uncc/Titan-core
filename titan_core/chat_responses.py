from __future__ import annotations

from titan_core.schemas import ChatRequest, ChatResponse

from .chat_actions import _action, _finalize_chat_response
from .chat_mode import is_development_assistant_mode, normalize_text
from .chat_tasks import format_when


GROUNDING_FALLBACK = "I don't know based on the information I have."
MAX_UPLOAD_CHARS = 120000
ALLOWED_UPLOAD_EXTENSIONS = {
    ".py", ".js", ".ts", ".html", ".css", ".json", ".md", ".txt",
    ".gd", ".tscn", ".yml", ".yaml",
}


def _finalize_with_metadata(
    user_message: str,
    response: ChatResponse,
    event_callback,
    route_used: str | None = None,
    source_type: str | None = None,
    source_status: str | None = None,
    source_label: str | None = None,
    source_names: list[str] | None = None,
    source_urls: list[str] | None = None,
    source_items: list[dict[str, object]] | None = None,
    confidence: str | None = None,
) -> ChatResponse:
    if route_used is not None:
        response.route_used = route_used
    if source_type is not None:
        response.source_type = source_type
    if source_status is not None:
        response.source_status = source_status
    if source_label is not None:
        response.source_label = source_label
    if source_names is not None:
        response.source_names = source_names
    if source_urls is not None:
        response.source_urls = source_urls
    if source_items is not None:
        response.source_items = source_items
    if confidence is not None:
        response.confidence = confidence
    finalized = _finalize_chat_response(user_message, response)
    event_callback(finalized)
    return finalized


def _source_metadata(
    *,
    source_type: str | None,
    source_status: str | None,
    source_names: list[str] | None = None,
    source_urls: list[str] | None = None,
    source_items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    label = None
    if source_type == "verified_web":
        label = "Source: Verified Web" if source_status == "retrieved" else "Source: Verified Web (Snippet)"
    elif source_type == "uploaded_file":
        label = "Source: Uploaded Verified File"
    elif source_type == "sitrep":
        label = "Source: Sitrep / Dashboard"
    elif source_type == "local_course_material":
        label = "Source: Local Course Material"
    elif source_type == "local_verified_source":
        label = "Source: Local Verified Source"

    return {
        "source_type": source_type,
        "source_status": source_status,
        "source_label": label,
        "source_names": source_names or [],
        "source_urls": source_urls or [],
        "source_items": source_items or [],
    }


def _format_verified_web_reply(verified_web: object, answer: str) -> str:
    lines = ["Based on verified web sources:", "", "Sources used:"]
    sources = getattr(verified_web, "sources", []) or []
    for source in sources[:3]:
        title = str(getattr(source, "title", "Verified source")).strip()
        score = int(getattr(source, "score", 0) or 0)
        url = str(getattr(source, "url", "")).strip()
        if url:
            lines.append(f"- {title} | score {score} | {url}")
        else:
            lines.append(f"- {title} | score {score}")
    lines.append("")
    lines.append("Answer:")
    lines.append(answer.strip())
    return "\n".join(lines)


def _verified_web_urls(verified_web: object | None) -> list[str]:
    if verified_web is None:
        return []
    urls: list[str] = []
    for source in getattr(verified_web, "sources", []) or []:
        url = str(getattr(source, "url", "")).strip()
        if url and url not in urls:
            urls.append(url)
    return urls


def _verified_web_source_items(verified_web: object | None) -> list[dict[str, object]]:
    if verified_web is None:
        return []
    items: list[dict[str, object]] = []
    for source in getattr(verified_web, "sources", []) or []:
        title = str(getattr(source, "title", "Verified source")).strip()
        url = str(getattr(source, "url", "")).strip()
        score = int(getattr(source, "score", 0) or 0)
        if not title or not url:
            continue
        items.append({"title": title, "url": url, "score": score})
    return items


def _missing_credible_web_source_reply(verified_web: object | None) -> str:
    if verified_web is not None and str(getattr(verified_web, "failure_reason", "") or "") == "below_threshold":
        return "I found web results, but none met the credibility threshold, so I'm not using them."
    return "I couldn't find a sufficiently credible verified web source for that."


def sanitize_uploaded_file(req: ChatRequest) -> tuple[str | None, str | None, str | None]:
    file_name = (req.file_name or "").strip()
    file_content = req.file_content

    if not file_name and not file_content:
        return None, None, None

    if not file_name or file_content is None:
        return None, None, "The uploaded file is incomplete. Please reattach it and try again."

    lowered_name = file_name.lower()
    if not any(lowered_name.endswith(ext) for ext in ALLOWED_UPLOAD_EXTENSIONS):
        return None, None, "That file type is not supported for verified chat grounding or Development Assistant review."

    cleaned_content = file_content.replace("\x00", "")
    if len(cleaned_content) > MAX_UPLOAD_CHARS:
        cleaned_content = cleaned_content[:MAX_UPLOAD_CHARS]

    return file_name, cleaned_content, None


def asks_for_dev_review(text: str) -> bool:
    normalized = normalize_text(text)
    return any(
        phrase in normalized
        for phrase in (
            "review",
            "check this file",
            "look over this file",
            "look at this file",
        )
    )


def development_missing_context_response() -> ChatResponse:
    return ChatResponse(
        reply=(
            "I don't know based on the information I have. "
            "Please attach the file you want reviewed or paste the relevant code and error message."
        ),
        proposed_actions=[],
    )


def missing_source_reply(intent: str, payload: dict) -> str:
    config = payload.get("configuration", {})
    needs_canvas = intent in {"next_class", "must_do_today", "still_open", "study_next", "daily_plan", "next_deadline", "daily_overview"}
    needs_schedule = intent in {"next_class", "schedule_today", "daily_plan", "daily_overview"}
    sources: list[str] = []

    if needs_canvas and not config.get("canvas_feed_configured"):
        sources.append("a configured Canvas ICS feed")
    if needs_schedule and not config.get("outlook_feed_configured"):
        sources.append("a configured Outlook ICS feed")
    if needs_schedule and not config.get("canvas_feed_configured") and "a configured Canvas ICS feed" not in sources:
        sources.append("a configured Canvas ICS feed")

    if sources:
        return f"{GROUNDING_FALLBACK} I would need {', '.join(sources)} to answer from real sitrep/dashboard data."

    return f"{GROUNDING_FALLBACK} The current sitrep/dashboard data does not include enough verified information for that."


def has_local_sitrep_sources(payload: dict) -> bool:
    config = payload.get("configuration", {})
    return bool(config.get("canvas_feed_configured") or config.get("outlook_feed_configured"))


def local_sitrep_empty_reply(payload: dict, message: str) -> str:
    generated_label = format_when(payload.get("generated_at"))
    return (
        f"Based on the current sitrep/dashboard data generated at {generated_label}, "
        f"{message}"
    )


def format_item_line(item: dict) -> str:
    title = item.get("title", "Untitled item")
    due = item.get("due_at")
    starts = item.get("starts_at")
    course = item.get("course_name")
    source = item.get("source")
    parts = [title]
    if course:
        parts.append(f"course: {course}")
    if due:
        parts.append(f"due: {format_when(due)}")
    elif starts:
        parts.append(f"time: {format_when(starts)}")
    if source:
        parts.append(f"source: {source}")
    return " | ".join(parts)


def personal_assistant_response(intent: str, payload: dict) -> ChatResponse:
    today = payload.get("today", [])
    must_do = payload.get("must_do_today", [])
    still_open = payload.get("still_open", [])
    suggested_blocks = payload.get("suggested_blocks", [])
    generated_at = payload.get("generated_at")
    generated_label = format_when(generated_at)
    config = payload.get("configuration", {})

    if intent == "refresh_sitrep":
        reply = (
            "I can refresh the sitrep from the current data sources. "
            "Use the Refresh Sitrep action or button to reload the dashboard data."
        )
        return ChatResponse(
            reply=reply,
            proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
        )

    if intent == "read_sitrep":
        reply = (
            "I can read the current sitrep aloud using the dashboard's Read Sitrep behavior. "
            f"The current sitrep/dashboard data was generated at {generated_label}."
        )
        return ChatResponse(
            reply=reply,
            proposed_actions=[_action("read_sitrep", "Read current sitrep aloud", implemented=True)],
        )

    if intent == "next_class":
        next_class = payload.get("next_class")
        if not isinstance(next_class, dict) or not next_class:
            if has_local_sitrep_sources(payload):
                return ChatResponse(
                    reply=local_sitrep_empty_reply(
                        payload,
                        "I do not currently see an upcoming class in the local sitrep.",
                    ),
                    proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
                )
            return ChatResponse(
                reply=missing_source_reply(intent, payload),
                proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
            )

        title = next_class.get("course_code") or next_class.get("course_name") or next_class.get("title") or "Untitled class"
        start_at = format_when(next_class.get("starts_at"))
        location = next_class.get("location")
        reply = (
            f"Based on the current sitrep/dashboard data generated at {generated_label}, "
            f"your next class is {title} starting {start_at}."
        )
        if location:
            reply += f" Location: {location}."
        return ChatResponse(
            reply=reply,
            proposed_actions=[
                _action("show_schedule", "Review today's schedule", implemented=False),
                _action("refresh_sitrep", "Refresh sitrep", implemented=True),
            ],
        )

    if intent == "schedule_today":
        if not today:
            if has_local_sitrep_sources(payload):
                return ChatResponse(
                    reply=local_sitrep_empty_reply(payload, "I do not see any scheduled items for today."),
                    proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
                )
            return ChatResponse(
                reply=missing_source_reply(intent, payload),
                proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
            )
        lines = [f"Based on the current sitrep/dashboard data generated at {generated_label}, your schedule today includes {len(today)} item(s):"]
        lines.extend(f"- {format_item_line(item)}" for item in today[:5])
        return ChatResponse(
            reply="\n".join(lines),
            proposed_actions=[
                _action("show_schedule", "Review today's schedule", implemented=False),
                _action("refresh_sitrep", "Refresh sitrep", implemented=True),
            ],
        )

    if intent == "must_do_today":
        if not must_do:
            if has_local_sitrep_sources(payload):
                return ChatResponse(
                    reply=local_sitrep_empty_reply(payload, "I do not see any must-do items due today."),
                    proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
                )
            return ChatResponse(
                reply=missing_source_reply(intent, payload),
                proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
            )
        lines = [f"Based on the current sitrep/dashboard data generated at {generated_label}, these are your must-do items for today:"]
        lines.extend(f"- {format_item_line(item)}" for item in must_do[:5])
        return ChatResponse(
            reply="\n".join(lines),
            proposed_actions=[
                _action("show_must_do", "Review must-do tasks", implemented=False),
                _action("build_study_plan", "Build study plan", implemented=False),
            ],
        )

    if intent == "still_open":
        if not still_open:
            if has_local_sitrep_sources(payload):
                return ChatResponse(
                    reply=local_sitrep_empty_reply(payload, "I do not see any still-open tasks right now."),
                    proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
                )
            return ChatResponse(
                reply=missing_source_reply(intent, payload),
                proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
            )
        lines = [f"Based on the current sitrep/dashboard data generated at {generated_label}, these open items still need attention:"]
        lines.extend(f"- {format_item_line(item)}" for item in still_open[:6])
        return ChatResponse(
            reply="\n".join(lines),
            proposed_actions=[
                _action("show_still_open", "Review open tasks", implemented=False),
                _action("build_study_plan", "Build study plan", implemented=False),
            ],
        )

    if intent == "study_next":
        if not suggested_blocks:
            if still_open:
                return ChatResponse(
                    reply=(
                        f"Based on the current sitrep/dashboard data generated at {generated_label}, "
                        "I don't know which study block to recommend because no suggested block is available yet."
                    ),
                    proposed_actions=[_action("build_study_plan", "Review suggested study blocks", implemented=False)],
                )
            return ChatResponse(
                reply=missing_source_reply(intent, payload),
                proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
            )
        block = suggested_blocks[0]
        reply = (
            f"Based on the current sitrep/dashboard data generated at {generated_label}, "
            f"your next study block is {block.get('title', 'Study block')} starting {format_when(block.get('starts_at'))}. "
            f"Reason: {block.get('reason', 'No reason listed')}."
        )
        return ChatResponse(
            reply=reply,
            proposed_actions=[
                _action("build_study_plan", "Review suggested study blocks", implemented=False),
                _action("show_still_open", "Review open tasks", implemented=False),
            ],
        )

    if intent == "daily_plan":
        if not today and not must_do and not suggested_blocks:
            if has_local_sitrep_sources(payload):
                return ChatResponse(
                    reply=local_sitrep_empty_reply(payload, "I do not see any schedule, must-do, or study-block items right now."),
                    proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
                )
            return ChatResponse(
                reply=missing_source_reply(intent, payload),
                proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
            )
        lines = [f"Based on the current sitrep/dashboard data generated at {generated_label}, here is your grounded plan for today:"]
        if today:
            lines.append(f"- Schedule items today: {len(today)}")
        if must_do:
            lines.append(f"- Must-do items today: {len(must_do)}")
            lines.extend(f"  {index + 1}. {format_item_line(item)}" for index, item in enumerate(must_do[:3]))
        if suggested_blocks:
            lines.append(f"- Suggested next study block: {suggested_blocks[0].get('title', 'Study block')} at {format_when(suggested_blocks[0].get('starts_at'))}")
        return ChatResponse(
            reply="\n".join(lines),
            proposed_actions=[
                _action("show_must_do", "Review must-do tasks", implemented=False),
                _action("build_study_plan", "Review suggested study blocks", implemented=False),
                _action("refresh_sitrep", "Refresh sitrep", implemented=True),
            ],
        )

    if intent == "next_deadline":
        candidates = [item for item in must_do if item.get("due_at")] + [item for item in still_open if item.get("due_at")]
        if not candidates:
            if has_local_sitrep_sources(payload):
                return ChatResponse(
                    reply=local_sitrep_empty_reply(payload, "I do not see any upcoming deadlines."),
                    proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
                )
            return ChatResponse(
                reply=missing_source_reply(intent, payload),
                proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
            )
        candidates.sort(key=lambda item: item.get("due_at") or "")
        next_item = candidates[0]
        reply = (
            f"Based on the current sitrep/dashboard data generated at {generated_label}, "
            f"your next listed deadline is {next_item.get('title', 'Untitled item')} due {format_when(next_item.get('due_at'))}."
        )
        return ChatResponse(
            reply=reply,
            proposed_actions=[
                _action("show_must_do", "Review must-do tasks", implemented=False),
                _action("show_still_open", "Review open tasks", implemented=False),
            ],
        )

    if intent == "daily_overview":
        if not today and not must_do and not suggested_blocks:
            if has_local_sitrep_sources(payload):
                return ChatResponse(
                    reply=local_sitrep_empty_reply(payload, "I do not see any scheduled items, must-do tasks, or suggested study blocks for today."),
                    proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
                )
            return ChatResponse(
                reply=missing_source_reply(intent, payload),
                proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
            )
        lines = [f"Based on the current sitrep/dashboard data generated at {generated_label}:"]
        lines.append(f"- Scheduled today: {len(today)} item(s)")
        lines.append(f"- Must-do today: {len(must_do)} item(s)")
        if must_do:
            lines.append(f"- Top must-do: {format_item_line(must_do[0])}")
        if suggested_blocks:
            lines.append(
                f"- Suggested next study block: {suggested_blocks[0].get('title', 'Study block')} at {format_when(suggested_blocks[0].get('starts_at'))}"
            )
        return ChatResponse(
            reply="\n".join(lines),
            proposed_actions=[
                _action("show_schedule", "Review today's schedule", implemented=False),
                _action("show_must_do", "Review must-do tasks", implemented=False),
                _action("build_study_plan", "Review suggested study blocks", implemented=False),
            ],
        )

    return ChatResponse(reply=GROUNDING_FALLBACK, proposed_actions=[])


def personal_unknown_response(text: str) -> ChatResponse:
    normalized = normalize_text(text)
    if any(word in normalized for word in ("canvas", "assignment", "deadline", "class", "schedule", "study", "task")):
        return ChatResponse(
            reply=f"{GROUNDING_FALLBACK} I would need current sitrep/dashboard data to answer that.",
            proposed_actions=[_action("refresh_sitrep", "Refresh sitrep", implemented=True)],
        )
    if any(word in normalized for word in ("email", "inbox", "mail")):
        return ChatResponse(
            reply=f"{GROUNDING_FALLBACK} I would need an email integration to answer from real inbox data.",
            proposed_actions=[],
        )
    if any(word in normalized for word in ("weather", "temperature", "forecast")):
        return ChatResponse(
            reply=f"{GROUNDING_FALLBACK} I would need a working weather source to answer that reliably.",
            proposed_actions=[],
        )
    return ChatResponse(reply=GROUNDING_FALLBACK, proposed_actions=[])
