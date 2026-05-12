from __future__ import annotations

import re
from datetime import datetime, timedelta

from titan_core.schemas import ChatResponse, TaskRecord
from titan_core.task_store import create_task, list_tasks, reschedule_task, update_task_status

from .chat_mode import normalize_text


GROUNDING_FALLBACK = "I don't know based on the information I have."
WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def format_when(value: str | None) -> str:
    if not value:
        return "no time listed"
    try:
        return datetime.fromisoformat(value).strftime("%A, %B %d at %I:%M %p")
    except ValueError:
        return value


def parse_due_phrase(text: str, now: datetime) -> datetime | None:
    candidate = (text or "").strip().rstrip(".")
    if not candidate:
        return None

    lowered = normalize_text(candidate)
    date_match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:\s+(.+))?", lowered)
    if date_match:
        year, month, day, time_part = date_match.groups()
        try:
            base = datetime(int(year), int(month), int(day), 9, 0)
        except ValueError:
            return None
        if time_part:
            parsed = parse_time_phrase(time_part)
            if parsed is None:
                return None
            hour, minute = parsed
            base = base.replace(hour=hour, minute=minute)
        return base

    base: datetime | None = None
    time_part = ""

    if lowered.startswith("tomorrow"):
        base = now + timedelta(days=1)
        time_part = lowered[len("tomorrow"):].strip()
    elif lowered.startswith("today"):
        base = now
        time_part = lowered[len("today"):].strip()
    else:
        for weekday, weekday_num in WEEKDAY_INDEX.items():
            if lowered.startswith(weekday):
                days_ahead = (weekday_num - now.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                base = now + timedelta(days=days_ahead)
                time_part = lowered[len(weekday):].strip()
                break

    if base is None:
        return None

    hour = 9
    minute = 0
    if time_part:
        parsed = parse_time_phrase(time_part)
        if parsed is None:
            return None
        hour, minute = parsed

    return base.replace(hour=hour, minute=minute, second=0, microsecond=0)


def parse_time_phrase(text: str) -> tuple[int, int] | None:
    cleaned = normalize_text(text).replace("at ", "", 1)
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", cleaned)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridiem = match.group(3)

    if minute > 59:
        return None

    if meridiem:
        if hour < 1 or hour > 12:
            return None
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
    elif hour > 23:
        return None

    return hour, minute


def format_task_line(task: TaskRecord, now: datetime) -> str:
    due_label = format_when(task.due_date)
    overdue = ""
    if task.status == "open" and task.due_date:
        try:
            if datetime.fromisoformat(task.due_date) < now:
                overdue = " | overdue"
        except ValueError:
            overdue = ""
    return f"- [{task.status}] {task.title} | id: {task.task_id} | due: {due_label}{overdue}"


def task_create_response(clean_text: str, now: datetime) -> ChatResponse | None:
    match = re.match(r"(?i)^add task:\s*(.+?)(?:\s+due\s+(.+))?$", clean_text.strip())
    if not match:
        return None

    title = (match.group(1) or "").strip()
    due_phrase = (match.group(2) or "").strip()

    if not title:
        return ChatResponse(reply="Please include a task title after `add task:`.", proposed_actions=[])

    due_value = None
    if due_phrase:
        parsed_due = parse_due_phrase(due_phrase, now)
        if parsed_due is None:
            return ChatResponse(
                reply=(
                    f"{GROUNDING_FALLBACK} Please give the due date in a supported format like "
                    "`tomorrow 8pm`, `Friday 6pm`, or `2026-05-01 20:00`."
                ),
                proposed_actions=[],
            )
        due_value = parsed_due.isoformat()

    task = create_task(title=title, due_date=due_value, priority=0)
    return ChatResponse(
        reply=f"Added task `{task.title}` with due date {format_when(task.due_date)}.",
        proposed_actions=[],
    )


def task_list_response(clean_text: str, now: datetime) -> ChatResponse | None:
    if normalize_text(clean_text) not in {"show my tasks", "show tasks", "list my tasks", "list tasks"}:
        return None

    tasks = list_tasks(include_completed=True)
    if not tasks:
        return ChatResponse(reply="You do not have any saved tasks yet.", proposed_actions=[])

    open_tasks = [task for task in tasks if task.status == "open"]
    completed_count = len(tasks) - len(open_tasks)
    lines = [f"You have {len(open_tasks)} open task(s) and {completed_count} completed task(s)."]
    lines.extend(format_task_line(task, now) for task in open_tasks[:10])
    return ChatResponse(reply="\n".join(lines), proposed_actions=[])


def task_complete_response(clean_text: str) -> ChatResponse | None:
    match = re.match(r"(?i)^(?:mark task complete|complete task):\s*(.+)$", clean_text.strip())
    if not match:
        return None

    task_ref = match.group(1).strip()
    if not task_ref:
        return ChatResponse(reply="Please tell me which task to mark complete.", proposed_actions=[])

    task = update_task_status(task_ref, "completed")
    if task is None:
        return ChatResponse(reply=f"{GROUNDING_FALLBACK} I could not find a saved task matching that title or task id.", proposed_actions=[])

    return ChatResponse(reply=f"Marked task `{task.title}` complete.", proposed_actions=[])


def task_move_response(clean_text: str, now: datetime) -> ChatResponse | None:
    match = re.match(r"(?i)^(?:move task|reschedule task):\s*(.+?)\s+to\s+(.+)$", clean_text.strip())
    if not match:
        return None

    task_ref = match.group(1).strip()
    due_phrase = match.group(2).strip()
    if not task_ref or not due_phrase:
        return ChatResponse(reply="Please provide both the task title and the new due time.", proposed_actions=[])

    parsed_due = parse_due_phrase(due_phrase, now)
    if parsed_due is None:
        return ChatResponse(
            reply=(
                f"{GROUNDING_FALLBACK} Please give the new due date in a supported format like "
                "`tomorrow 8pm`, `Friday 6pm`, or `2026-05-01 20:00`."
            ),
            proposed_actions=[],
        )

    task = reschedule_task(task_ref, parsed_due.isoformat())
    if task is None:
        return ChatResponse(reply=f"{GROUNDING_FALLBACK} I could not find a saved task matching that title or task id.", proposed_actions=[])

    return ChatResponse(reply=f"Moved task `{task.title}` to {format_when(task.due_date)}.", proposed_actions=[])


def task_command_response(clean_text: str, now: datetime) -> ChatResponse | None:
    response = task_create_response(clean_text, now)
    if response is not None:
        return response

    response = task_list_response(clean_text, now)
    if response is not None:
        return response

    response = task_complete_response(clean_text)
    if response is not None:
        return response

    response = task_move_response(clean_text, now)
    if response is not None:
        return response

    return None
