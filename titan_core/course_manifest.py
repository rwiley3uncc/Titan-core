from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

SUPPORTED_COURSE_SOURCE_EXTENSIONS = {".md", ".txt", ".json"}


def default_courses_root() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "courses"


class CourseManifest(BaseModel):
    course_id: str
    course_name: str
    term: str
    instructor: str | None = None
    source_files: list[str] = Field(default_factory=list)
    assignment_links: list[str] = Field(default_factory=list)
    notes: str = ""
    created_at: str
    updated_at: str

    @field_validator("course_id", "course_name", "term", mode="before")
    @classmethod
    def _non_empty_text(cls, value: object) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("value must be non-empty")
        return text

    @field_validator("source_files", mode="before")
    @classmethod
    def _normalize_source_files(cls, value: object) -> list[str]:
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise ValueError("source_files must be a list")
        normalized: list[str] = []
        for entry in value:
            text = str(entry or "").strip().replace("\\", "/")
            if not text:
                continue
            normalized.append(text)
        return normalized

    @field_validator("assignment_links", mode="before")
    @classmethod
    def _normalize_assignment_links(cls, value: object) -> list[str]:
        if value in (None, ""):
            return []
        if not isinstance(value, list):
            raise ValueError("assignment_links must be a list")
        return [str(entry or "").strip() for entry in value if str(entry or "").strip()]

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _validate_timestamp(cls, value: object) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("timestamp must be non-empty")
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return text


@dataclass(frozen=True)
class CourseManifestRecord:
    manifest_path: Path
    course_root: Path
    manifest: CourseManifest

    @property
    def source_paths(self) -> list[Path]:
        results: list[Path] = []
        for rel_path in self.manifest.source_files:
            results.append((self.course_root / rel_path).resolve())
        return results


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("course manifest root must be a JSON object")
    return payload


def load_course_manifest(path: Path) -> CourseManifestRecord:
    manifest_path = path.resolve()
    payload = _load_json(manifest_path)
    manifest = CourseManifest.model_validate(payload)
    course_root = manifest_path.parent.resolve()
    return CourseManifestRecord(
        manifest_path=manifest_path,
        course_root=course_root,
        manifest=manifest,
    )


def iter_course_manifest_paths(courses_root: Path | None = None) -> list[Path]:
    root = (courses_root or default_courses_root()).resolve()
    if not root.exists():
        return []
    return sorted(path.resolve() for path in root.rglob("course_manifest.json") if path.is_file())


def list_course_manifests(courses_root: Path | None = None) -> list[CourseManifestRecord]:
    return [load_course_manifest(path) for path in iter_course_manifest_paths(courses_root)]


def validate_course_manifest_record(record: CourseManifestRecord) -> list[str]:
    issues: list[str] = []
    manifest = record.manifest

    if record.course_root.name != manifest.course_id:
        issues.append(
            f"{record.manifest_path}: course_id '{manifest.course_id}' should match folder name '{record.course_root.name}' for the local-first course workspace model."
        )

    for rel_path, resolved_path in zip(manifest.source_files, record.source_paths):
        rel_candidate = Path(rel_path)
        if rel_candidate.is_absolute():
            issues.append(f"{record.manifest_path}: source_files entry must be relative, not absolute: {rel_path}")
            continue
        if rel_candidate.suffix.lower() not in SUPPORTED_COURSE_SOURCE_EXTENSIONS:
            issues.append(
                f"{record.manifest_path}: unsupported source_files extension for retrieval MVP: {rel_path}. "
                f"Supported extensions: {', '.join(sorted(SUPPORTED_COURSE_SOURCE_EXTENSIONS))}."
            )
            continue
        try:
            resolved_path.relative_to(record.course_root)
        except ValueError:
            issues.append(f"{record.manifest_path}: source_files entry escapes the course root: {rel_path}")
            continue
        if not resolved_path.exists():
            issues.append(f"{record.manifest_path}: source_files entry does not exist: {rel_path}")

    return issues


def example_course_manifest_payload() -> dict[str, object]:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "course_id": "example-student-ops",
        "course_name": "Example Student Ops Course",
        "term": "2026 Spring",
        "instructor": "Optional Instructor",
        "source_files": ["notes/example_note.md"],
        "assignment_links": [],
        "notes": "Copy this folder and replace the metadata with your real course information.",
        "created_at": now,
        "updated_at": now,
    }
