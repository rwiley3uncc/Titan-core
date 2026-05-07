from __future__ import annotations

from pathlib import Path

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
    validate_writable_paths,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    issues = []
    issues.extend(validate_imports(["fastapi", "sqlalchemy", "requests", "pydantic", "titan_ai", "titan_shared", "titan_core", "titan_battlebuddy"]))
    issues.extend(validate_directories([root / "titan_ui", root / "data", root / "docs"]))
    issues.extend(validate_files([root / "requirements.txt", root / "start_titan.ps1", root / "start_battlebuddy.ps1"]))
    issues.extend(validate_writable_paths([root / "data"]))
    return print_validation_report("Titan BattleBuddy Environment Validation", issues, python_runtime_summary())


if __name__ == "__main__":
    raise SystemExit(main())
