from __future__ import annotations

import re
from typing import Iterable


QUESTION_STARTERS = ("what ", "where ", "when ", "why ", "how ", "who ", "which ", "do ", "does ", "did ", "is ", "are ", "can ", "could ", "would ", "should ")
PERSONAL_ASSISTANT_MODES = {"personal_general", "personal_productivity", "personal_builder", "personal_family"}
TODAY_TOKENS = {"today", "toda", "tody", "todays"}
SCHEDULE_TOKENS = {"schedule", "calendar", "agenda"}
PRIORITY_TOKENS = {"priority", "priorities", "important", "focus", "attention"}
TASK_TOKENS = {"task", "tasks", "must", "need", "due"}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def tokenize(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", normalize_text(text)) if len(w) > 1}


def is_question(text: str) -> bool:
    lowered = normalize_text(text)
    return lowered.endswith("?") or lowered.startswith(QUESTION_STARTERS)


def safe_mode(req_mode: str | None) -> str:
    return req_mode if req_mode in {"personal_general", "personal_productivity", "personal_builder", "personal_family", "development_assistant"} else "personal_general"


def is_personal_assistant_mode(mode: str) -> bool:
    return mode in PERSONAL_ASSISTANT_MODES


def is_development_assistant_mode(mode: str) -> bool:
    return mode == "development_assistant"


def should_use_personal_memory(mode: str) -> bool:
    return is_personal_assistant_mode(mode)


def classify_route(text: str, mode: str, personal_intent: str | None = None) -> str:
    normalized = normalize_text(text)

    if personal_intent:
        return "personal_grounded"

    if is_development_assistant_mode(mode):
        return "development_assistant"

    if is_question(text):
        return "verified_knowledge"

    knowledge_hints = (
        "explain",
        "definition",
        "define",
        "what is",
        "how does",
        "why does",
        "who is",
        "math",
        "calculus",
        "physics",
        "chemistry",
        "history",
        "coding",
        "programming",
        "fastapi",
        "python",
        "research",
    )
    if any(hint in normalized for hint in knowledge_hints):
        return "verified_knowledge"

    personal_hints = (
        "schedule",
        "calendar",
        "task",
        "deadline",
        "sitrep",
        "reminder",
        "assignment",
        "study",
        "class",
    )
    if any(hint in normalized for hint in personal_hints):
        return "personal_grounded"

    return "unsupported"


def has_token(tokens: set[str], *options: str) -> bool:
    return any(option in tokens for option in options)


def has_today_reference(normalized: str, tokens: set[str]) -> bool:
    return bool(TODAY_TOKENS & tokens) or "today's" in normalized


def detect_personal_intent(text: str) -> str | None:
    normalized = normalize_text(text)
    tokens = tokenize(normalized)
    has_today = has_today_reference(normalized, tokens)
    asks_what = "what" in tokens or "whats" in tokens or "what's" in normalized
    asks_can_you_see = "can you see" in normalized

    if any(phrase in normalized for phrase in ("refresh my sitrep", "refresh sitrep", "reload sitrep", "update sitrep")):
        return "refresh_sitrep"
    if any(phrase in normalized for phrase in ("read my sitrep", "read sitrep", "speak sitrep", "say my sitrep")):
        return "read_sitrep"
    if any(phrase in normalized for phrase in (
        "what is my next class",
        "what's my next class",
        "whats my next class",
        "when is my next class",
        "when's my next class",
        "when is the next class",
        "what class is next",
        "next class",
    )):
        return "next_class"
    if "canvas calendar" in normalized and ("next class" in normalized or asks_can_you_see):
        return "next_class"
    if any(phrase in normalized for phrase in ("what should i study next", "what should i work on next", "study next", "next study block")):
        return "study_next"
    if any(phrase in normalized for phrase in ("show my open tasks", "show open tasks", "what is still open", "what's still open", "still open", "open tasks")):
        return "still_open"
    if any(phrase in normalized for phrase in (
        "summarize my must-do tasks",
        "summarize my must do tasks",
        "must-do tasks",
        "must do tasks",
        "what must i do today",
        "due today",
    )):
        return "must_do_today"
    if has_today and (
        "what needs attention" in normalized
        or "what is important" in normalized
        or "what's important" in normalized
        or "priorities today" in normalized
        or "what should i focus on" in normalized
        or "what should i focus on today" in normalized
        or "on the table today" in normalized
    ):
        return "daily_plan"
    if has_today and (PRIORITY_TOKENS & tokens) and ("what" in tokens or "whats" in tokens or "what's" in normalized):
        return "daily_plan"
    if any(phrase in normalized for phrase in ("make me a study plan", "make me a daily plan", "build me a study plan", "build a study plan", "daily plan", "plan my day")):
        return "daily_plan"
    if any(phrase in normalized for phrase in ("next deadline", "what is my next deadline", "what's my next deadline")):
        return "next_deadline"
    if "canvas calendar" in normalized and asks_what:
        if "due" in tokens or "assignment" in tokens or "deadline" in tokens:
            return "must_do_today" if has_today else "next_deadline"
        if "open" in tokens or "still" in tokens:
            return "still_open"
        if "class" in tokens:
            return "next_class"
        return "schedule_today"
    if any(phrase in normalized for phrase in (
        "what do i need to do today",
        "what should i do today",
        "what is on today's schedule",
        "what's on today's schedule",
        "what is on todays schedule",
        "what's on todays schedule",
        "what is on today",
        "what's on today",
        "whats on today",
        "what do i have today",
        "what is on my canvas calendar",
        "what's on my canvas calendar",
        "what is on the canvas calendar",
        "what is my schedule today",
        "what's my schedule today",
    )):
        return "daily_overview"
    if asks_what and ("schedule" in tokens or "calendar" in tokens) and "class" in tokens:
        return "next_class"
    if has_today and (
        has_token(tokens, *SCHEDULE_TOKENS)
        or "on the schedule" in normalized
        or "today schedule" in normalized
        or "todays schedule" in normalized
        or "calendar today" in normalized
        or "agenda today" in normalized
        or "due today" in normalized
    ):
        return "schedule_today"
    if has_today and "schedule" in tokens:
        return "schedule_today"
    if has_today and ("on the table today" in normalized or ("have" in tokens and "what" in tokens)):
        return "daily_overview"
    if has_today and has_token(tokens, *TASK_TOKENS) and ("what" in tokens or "whats" in tokens or "what's" in normalized):
        return "daily_plan"
    if has_today and "good morning" in normalized and ("table" in tokens or has_token(tokens, *SCHEDULE_TOKENS, *PRIORITY_TOKENS)):
        return "daily_overview"
    if "what is on the schedule" in normalized or "whats on the schedule" in normalized or "what's on the schedule" in normalized:
        return "schedule_today"

    return None
