from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import tempfile
from pathlib import Path
import urllib.error
import urllib.request
from unittest import mock

from titan_core.titan_ai_imports import enable_titan_ai_imports
from titan_core.titan_shared_imports import ensure_titan_shared_on_path

enable_titan_ai_imports()
ensure_titan_shared_on_path()

from titan_shared.runtime_validation import (  # noqa: E402
    print_validation_report,
    python_runtime_summary,
    validate_directories,
    validate_files,
    validate_imports,
)
from titan_shared.contracts.titan_event import load_titan_events_from_path  # noqa: E402


def _http_ok(url: str, *, timeout_seconds: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            return int(getattr(response, "status", 0)) == 200
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return False


def _run_startup_gate(root: Path, *, host: str, port: int, timeout_seconds: float) -> int:
    title = "Titan BattleBuddy Startup Gate"
    details = python_runtime_summary()
    details.update({
        "host": host,
        "port": str(port),
        "startup_command": f"{sys.executable} -m uvicorn titan_battlebuddy.main:app --host {host} --port {port}",
    })
    issues: list[str] = []
    process: subprocess.Popen[str] | None = None
    health_url = f"http://{host}:{port}/health"

    if _http_ok(health_url):
        issues.append(f"ENVIRONMENT_ISSUE: Startup gate requires {health_url} to be free before validation.")
        return print_validation_report(title, issues, details)

    env = dict(os.environ)

    with tempfile.TemporaryDirectory(prefix="titan-battlebuddy-startup-gate-") as temp_dir:
        temp_root = Path(temp_dir)
        temp_db_path = temp_root / f"validation_battlebuddy_{port}.db"
        temp_event_path = temp_root / "events" / "titan_events.jsonl"
        temp_archive_dir = temp_root / "events" / "archive"
        env.setdefault("DATABASE_URL", f"sqlite:///{temp_db_path.as_posix()}")
        startup_script = "\n".join([
            "from pathlib import Path",
            "import uvicorn",
            "import titan_core.event_log as event_log",
            f"event_log.EVENT_LOG_PATH = Path(r'{str(temp_event_path)}')",
            f"event_log.EVENTS_DIR = Path(r'{str(temp_event_path.parent)}')",
            f"event_log.EVENT_ARCHIVE_DIR = Path(r'{str(temp_archive_dir)}')",
            "from titan_battlebuddy.main import app",
            f"uvicorn.run(app, host={host!r}, port={port}, log_level='warning')",
        ])

        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    startup_script,
                ],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
        except OSError as error:
            issues.append(f"ENVIRONMENT_ISSUE: Could not start BattleBuddy startup gate process: {error}")
            return print_validation_report(title, issues, details)

        started = False
        try:
            deadline = time.perf_counter() + timeout_seconds
            while time.perf_counter() < deadline:
                if process.poll() is not None:
                    stdout, stderr = process.communicate(timeout=2)
                    issues.append("FAIL: BattleBuddy startup gate process exited before the health endpoint became ready.")
                    if stdout.strip():
                        issues.append(f"FAIL: BattleBuddy startup stdout: {stdout.strip()}")
                    if stderr.strip():
                        issues.append(f"FAIL: BattleBuddy startup stderr: {stderr.strip()}")
                    return print_validation_report(title, issues, details)
                if _http_ok(health_url):
                    started = True
                    break
                time.sleep(0.5)

            if not started:
                issues.append(f"FAIL: BattleBuddy startup gate did not reach {health_url} within {timeout_seconds:.1f}s.")
                return print_validation_report(title, issues, details)
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)

        if _http_ok(health_url):
            issues.append("FAIL: BattleBuddy startup gate left the health endpoint running after shutdown.")

        if temp_event_path.exists() and not str(temp_event_path).startswith(temp_dir):
            issues.append("FAIL: BattleBuddy startup gate wrote event data outside the temporary validation root.")

        return print_validation_report(title, issues, details)


def validate_battlebuddy_event_helper(root: Path) -> list[str]:
    issues: list[str] = []

    try:
        from titan_core.event_log import (
            DEFAULT_MAX_EVENT_LOG_BYTES,
            emit_battlebuddy_event,
            enforce_event_log_retention,
        )
    except Exception as exc:
        return [f"FAIL: Could not import titan_core.event_log safely: {exc}"]

    with tempfile.TemporaryDirectory(prefix="titan-core-events-") as temp_dir:
        event_path = Path(temp_dir) / "titan_events.jsonl"
        wrote = emit_battlebuddy_event(
            subsystem="battlebuddy",
            severity="NOTICE",
            event_type="validation",
            summary="BattleBuddy event helper validation record.",
            details="Validation-only summary.",
            confidence=0.5,
            risk="low",
            status="completed",
            log_path=event_path,
        )
        if not wrote:
            issues.append("FAIL: BattleBuddy event helper did not report a successful write.")
            return issues

        events = load_titan_events_from_path(event_path)
        if len(events) != 1:
            issues.append("FAIL: BattleBuddy event helper did not produce one compatible TitanEvent record.")
            return issues

        payload = events[0].to_dict()
        if payload.get("source") != "battlebuddy":
            issues.append("FAIL: BattleBuddy event helper did not preserve the expected source field.")
        if payload.get("subsystem") != "battlebuddy":
            issues.append("FAIL: BattleBuddy event helper did not preserve the expected subsystem field.")
        if payload.get("event_type") != "validation":
            issues.append("FAIL: BattleBuddy event helper did not preserve the expected event_type field.")

        retention_path = Path(temp_dir) / "retention_validation.jsonl"
        archive_dir = Path(temp_dir) / "archive"
        for index in range(5):
            wrote = emit_battlebuddy_event(
                subsystem="battlebuddy",
                severity="INFO",
                event_type="retention_validation",
                summary=f"Retention event {index}",
                details=f"sequence={index}",
                confidence=0.5,
                risk="low",
                status="completed",
                log_path=retention_path,
                max_events=3,
                max_bytes=DEFAULT_MAX_EVENT_LOG_BYTES,
                archive_dir=archive_dir,
            )
            if not wrote:
                issues.append("FAIL: BattleBuddy retention validation could not append an event safely.")
                return issues

        retained_events = load_titan_events_from_path(retention_path)
        retained_summaries = [event.summary for event in retained_events]
        if len(retained_events) != 3:
            issues.append("FAIL: BattleBuddy event retention did not trim to the newest expected event count.")
        elif retained_summaries != ["Retention event 2", "Retention event 3", "Retention event 4"]:
            issues.append("FAIL: BattleBuddy event retention did not preserve the newest events in order.")

        archived_files = sorted(archive_dir.glob("*.jsonl"))
        if not archived_files:
            issues.append("FAIL: BattleBuddy event retention did not archive trimmed events safely.")

        oversize_path = Path(temp_dir) / "oversize_validation.jsonl"
        for index in range(4):
            wrote = emit_battlebuddy_event(
                subsystem="battlebuddy",
                severity="NOTICE",
                event_type="size_validation",
                summary=f"Size validation event {index}",
                details="X" * 400,
                confidence=0.4,
                risk="low",
                status="completed",
                log_path=oversize_path,
                max_events=10,
                max_bytes=700,
                archive_dir=archive_dir,
            )
            if not wrote:
                issues.append("FAIL: BattleBuddy size-retention validation could not append an event safely.")
                return issues

        oversize_events = load_titan_events_from_path(oversize_path)
        if not oversize_events:
            issues.append("FAIL: BattleBuddy size retention removed all recent events unexpectedly.")
        elif oversize_events[-1].summary != "Size validation event 3":
            issues.append("FAIL: BattleBuddy size retention did not preserve the newest event.")

        if not enforce_event_log_retention(Path(temp_dir) / "missing.jsonl"):
            issues.append("FAIL: BattleBuddy event retention should succeed safely for a missing log path.")

    return issues


def validate_battlebuddy_approval_helper(root: Path) -> list[str]:
    issues: list[str] = []

    try:
        from titan_core.approval_log import emit_approval_request
        from titan_shared.contracts.approval_request import load_approval_requests_from_path
    except Exception as exc:
        return [f"FAIL: Could not import BattleBuddy approval helper safely: {exc}"]

    with tempfile.TemporaryDirectory(prefix="titan-core-approvals-") as temp_dir:
        approval_path = Path(temp_dir) / "approval_requests.jsonl"
        wrote = emit_approval_request(
            source="battlebuddy",
            subsystem="battlebuddy",
            title="Review proposed action: open_vscode",
            summary="BattleBuddy proposed a constrained action for local review.",
            requested_action="open_vscode",
            risk="medium",
            confidence=0.75,
            requires_confirmation=True,
            status="pending",
            created_by="battlebuddy",
            metadata={
                "label": "Open VS Code",
                "app": "vscode",
                "log_user_message": "do not persist this",
            },
            log_path=approval_path,
        )
        if not wrote:
            issues.append("FAIL: BattleBuddy approval helper did not report a successful write.")
            return issues

        approvals = load_approval_requests_from_path(approval_path)
        if len(approvals) != 1:
            issues.append("FAIL: BattleBuddy approval helper did not produce one compatible ApprovalRequest record.")
            return issues

        payload = approvals[0].to_dict()
        if payload.get("source") != "battlebuddy":
            issues.append("FAIL: BattleBuddy approval helper did not preserve the expected source field.")
        if payload.get("requested_action") != "open_vscode":
            issues.append("FAIL: BattleBuddy approval helper did not preserve the expected requested_action field.")
        metadata = payload.get("metadata", {})
        if "log_user_message" in metadata:
            issues.append("FAIL: BattleBuddy approval helper should strip full user-message content from metadata.")

        duplicate_wrote = emit_approval_request(
            source="battlebuddy",
            subsystem="battlebuddy",
            title="Review proposed action: open_vscode",
            summary="BattleBuddy proposed a constrained action for local review.",
            requested_action="open_vscode",
            risk="medium",
            confidence=0.75,
            requires_confirmation=True,
            status="pending",
            created_by="battlebuddy",
            metadata={
                "label": "Open VS Code",
                "app": "vscode",
                "action_id": payload.get("metadata", {}).get("action_id", ""),
            },
            log_path=approval_path,
        )
        if not duplicate_wrote:
            issues.append("FAIL: BattleBuddy approval helper duplicate write path should still return safely.")
            return issues

        approvals_after_duplicate = load_approval_requests_from_path(approval_path)
        if len(approvals_after_duplicate) != 1:
            issues.append("FAIL: BattleBuddy approval helper should avoid duplicate pending approval records when possible.")

    return issues


def validate_battlebuddy_data_store_helpers(root: Path) -> list[str]:
    issues: list[str] = []

    try:
        from titan_core import calendar_store, dismissed_items_store, task_store
        from titan_core.schemas import CalendarSourceCreate, DismissedItemCreate
    except Exception as exc:
        return [f"FAIL: Could not import BattleBuddy data-store helpers safely: {exc}"]

    with tempfile.TemporaryDirectory(prefix="titan-core-data-store-validation-") as temp_dir:
        temp_root = Path(temp_dir)
        data_dir = temp_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        tasks_path = data_dir / "tasks.json"
        calendar_sources_path = data_dir / "calendar_sources.json"
        dismissed_items_path = data_dir / "dismissed_items.json"

        with mock.patch.object(task_store, "DATA_DIR", data_dir), mock.patch.object(task_store, "TASKS_PATH", tasks_path):
            created_task = task_store.create_task("Validation task", None, priority=2)
            if created_task.title != "Validation task":
                issues.append("FAIL: BattleBuddy task store did not preserve the created task title.")
            loaded_tasks = task_store.list_tasks(include_completed=True)
            if len(loaded_tasks) != 1:
                issues.append("FAIL: BattleBuddy task store did not persist the created task safely.")

        with mock.patch.object(calendar_store, "DATA_DIR", data_dir), mock.patch.object(calendar_store, "CALENDAR_SOURCES_PATH", calendar_sources_path):
            created_source = calendar_store.create_calendar_source(
                CalendarSourceCreate(
                    name="Validation Calendar",
                    type="other",
                    url="https://example.com/calendar.ics",
                    enabled=True,
                )
            )
            if created_source.name != "Validation Calendar":
                issues.append("FAIL: BattleBuddy calendar store did not preserve the created source name.")
            loaded_sources = calendar_store.list_calendar_sources()
            if not any(source.id == created_source.id for source in loaded_sources):
                issues.append("FAIL: BattleBuddy calendar store did not persist the created source safely.")

        with mock.patch.object(dismissed_items_store, "DATA_DIR", data_dir), mock.patch.object(
            dismissed_items_store,
            "DISMISSED_ITEMS_PATH",
            dismissed_items_path,
        ):
            dismissed_record = dismissed_items_store.dismiss_item(
                DismissedItemCreate(
                    item_id="validation-item-001",
                    title="Validation Item",
                    course="Validation Course",
                    reason="validation",
                )
            )
            if dismissed_record.item_id != "validation-item-001":
                issues.append("FAIL: BattleBuddy dismissed-items store did not preserve the item id safely.")
            if "validation-item-001" not in dismissed_items_store.dismissed_item_ids():
                issues.append("FAIL: BattleBuddy dismissed-items store did not persist the dismissed item safely.")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Titan BattleBuddy environment and startup validation.")
    parser.add_argument("--startup-gate", action="store_true", help="Run the launcher-neutral BattleBuddy startup gate.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for startup-gate validation.")
    parser.add_argument("--port", type=int, default=8001, help="Port for startup-gate validation.")
    parser.add_argument("--timeout-seconds", type=float, default=20.0, help="Startup-gate readiness timeout.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    if args.startup_gate:
        return _run_startup_gate(root, host=args.host, port=args.port, timeout_seconds=args.timeout_seconds)

    issues = []
    issues.extend(validate_imports(["fastapi", "sqlalchemy", "requests", "pydantic", "titan_ai", "titan_shared", "titan_core", "titan_battlebuddy"]))
    issues.extend(validate_directories([root / "titan_ui", root / "data", root / "docs"]))
    issues.extend(validate_files([root / "requirements.txt", root / "start_titan.ps1", root / "start_battlebuddy.ps1"]))
    issues.extend(validate_battlebuddy_approval_helper(root))
    issues.extend(validate_battlebuddy_data_store_helpers(root))
    issues.extend(validate_battlebuddy_event_helper(root))
    return print_validation_report("Titan BattleBuddy Environment Validation", issues, python_runtime_summary())


if __name__ == "__main__":
    raise SystemExit(main())
