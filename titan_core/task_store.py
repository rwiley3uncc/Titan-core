from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from titan_core.planning import PlannerItem
from titan_core.schemas import TaskRecord


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TASKS_PATH = DATA_DIR / "tasks.json"


def _ensure_store() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not TASKS_PATH.exists():
        TASKS_PATH.write_text("[]\n", encoding="utf-8")


def _load_tasks() -> list[TaskRecord]:
    _ensure_store()
    raw = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    tasks: list[TaskRecord] = []
    for item in raw:
        if isinstance(item, dict):
            try:
                tasks.append(TaskRecord(**item))
            except Exception:
                continue
    return tasks


def _save_tasks(tasks: list[TaskRecord]) -> None:
    _ensure_store()
    payload = [task.model_dump() for task in tasks]
    TASKS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def list_tasks(*, include_completed: bool = True) -> list[TaskRecord]:
    tasks = _load_tasks()
    if include_completed:
        return tasks
    return [task for task in tasks if task.status != "completed"]


def create_task(title: str, due_date: str | None, priority: int = 0) -> TaskRecord:
    now = datetime.now().isoformat()
    task = TaskRecord(
        task_id=uuid.uuid4().hex[:12],
        title=title.strip(),
        due_date=due_date,
        status="open",
        priority=priority,
        created_at=now,
        updated_at=now,
    )
    tasks = _load_tasks()
    tasks.append(task)
    _save_tasks(tasks)
    return task


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def find_task(task_ref: str, *, include_completed: bool = True) -> TaskRecord | None:
    normalized_ref = _normalize(task_ref)
    if not normalized_ref:
        return None

    tasks = list_tasks(include_completed=include_completed)

    for task in tasks:
        if _normalize(task.task_id) == normalized_ref:
            return task

    exact = [task for task in tasks if _normalize(task.title) == normalized_ref]
    if exact:
        return exact[0]

    partial = [task for task in tasks if normalized_ref in _normalize(task.title)]
    if len(partial) == 1:
        return partial[0]

    return None


def update_task_status(task_ref: str, status: str) -> TaskRecord | None:
    tasks = _load_tasks()
    task = find_task(task_ref, include_completed=True)
    if task is None:
        return None

    for index, current in enumerate(tasks):
        if current.task_id == task.task_id:
            tasks[index] = current.model_copy(update={"status": status, "updated_at": datetime.now().isoformat()})
            _save_tasks(tasks)
            return tasks[index]
    return None


def reschedule_task(task_ref: str, due_date: str | None) -> TaskRecord | None:
    tasks = _load_tasks()
    task = find_task(task_ref, include_completed=True)
    if task is None:
        return None

    for index, current in enumerate(tasks):
        if current.task_id == task.task_id:
            tasks[index] = current.model_copy(update={"due_date": due_date, "updated_at": datetime.now().isoformat()})
            _save_tasks(tasks)
            return tasks[index]
    return None


def tasks_as_planner_items() -> list[PlannerItem]:
    items: list[PlannerItem] = []
    for task in list_tasks(include_completed=True):
        due_at = None
        if task.due_date:
            try:
                due_at = datetime.fromisoformat(task.due_date)
            except ValueError:
                due_at = None
        items.append(
            PlannerItem(
                title=task.title,
                kind="reminder",
                due_at=due_at,
                source="titan_tasks",
                details=f"task_id: {task.task_id} | status: {task.status}",
                priority=task.priority,
                is_complete=task.status == "completed",
            )
        )
    return items
