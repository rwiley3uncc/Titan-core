from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from titan_core.course_manifest import (
    SUPPORTED_COURSE_SOURCE_EXTENSIONS,
    CourseManifestRecord,
    default_courses_root,
    list_course_manifests,
)


MAX_SOURCE_CHARS = 20000
CHUNK_CHARS = 900
CHUNK_OVERLAP = 120
MAX_HITS = 3
MIN_RETRIEVAL_SCORE = 2.0


@dataclass(frozen=True)
class CourseChunk:
    course_id: str
    course_name: str
    source_name: str
    source_path: Path
    chunk_id: str
    content: str
    modified_at: str


@dataclass(frozen=True)
class CourseRetrievalHit:
    course_id: str
    course_name: str
    source_name: str
    source_path: Path
    chunk_id: str
    content: str
    score: float
    modified_at: str

    def to_source_item(self) -> dict[str, object]:
        excerpt = self.content.strip()
        if len(excerpt) > 280:
            excerpt = f"{excerpt[:277].rstrip()}..."
        return {
            "course_id": self.course_id,
            "course_name": self.course_name,
            "source_name": self.source_name,
            "source_path": str(self.source_path),
            "chunk_id": self.chunk_id,
            "score": round(self.score, 2),
            "modified_at": self.modified_at,
            "excerpt": excerpt,
        }


@dataclass(frozen=True)
class CourseRetrievalResult:
    query: str
    hits: list[CourseRetrievalHit]
    confidence: str
    source_status: str
    summary: str
    latest_source_mtime: str | None
    course_count: int
    source_file_count: int
    indexed_chunk_count: int
    unsupported_files: list[str]

    @property
    def names(self) -> list[str]:
        names: list[str] = []
        for hit in self.hits:
            label = f"{hit.course_name}: {hit.source_name}"
            if label not in names:
                names.append(label)
        return names

    @property
    def context_text(self) -> str:
        sections = [
            "Local course retrieval context is active.",
            "Use only the retrieved course material below when answering.",
            "If the retrieved support is partial or weak, say that explicitly.",
            "",
        ]
        for index, hit in enumerate(self.hits, start=1):
            sections.extend(
                [
                    (
                        f"[Source {index}] course_id={hit.course_id} | "
                        f"course_name={hit.course_name} | file={hit.source_name} | "
                        f"score={hit.score:.2f} | modified_at={hit.modified_at}"
                    ),
                    hit.content.strip(),
                    "",
                ]
            )
        return "\n".join(sections).strip()

    @property
    def source_items(self) -> list[dict[str, object]]:
        return [hit.to_source_item() for hit in self.hits]


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9_]+", _normalize_text(text)) if len(token) > 1}


def _file_modified_at(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")


def _read_source_text(path: Path) -> str:
    suffix = path.suffix.lower()
    raw_text = path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".json":
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            return raw_text[:MAX_SOURCE_CHARS]
        return json.dumps(parsed, indent=2, ensure_ascii=True)[:MAX_SOURCE_CHARS]
    return raw_text[:MAX_SOURCE_CHARS]


def _chunk_text(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    length = len(normalized)
    while start < length:
        end = min(length, start + CHUNK_CHARS)
        if end < length:
            split_at = normalized.rfind("\n", start, end)
            if split_at <= start:
                split_at = normalized.rfind(" ", start, end)
            if split_at > start + 200:
                end = split_at
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def _iter_chunks(records: list[CourseManifestRecord]) -> tuple[list[CourseChunk], list[str], str | None]:
    chunks: list[CourseChunk] = []
    unsupported_files: list[str] = []
    latest_source_mtime: str | None = None

    for record in records:
        for rel_path, source_path in zip(record.manifest.source_files, record.source_paths):
            if Path(rel_path).suffix.lower() not in SUPPORTED_COURSE_SOURCE_EXTENSIONS:
                unsupported_files.append(str((record.course_root / rel_path).resolve()))
                continue
            if not source_path.exists():
                continue
            modified_at = _file_modified_at(source_path)
            latest_source_mtime = max(latest_source_mtime or modified_at, modified_at)
            source_text = _read_source_text(source_path)
            for index, chunk in enumerate(_chunk_text(source_text), start=1):
                chunks.append(
                    CourseChunk(
                        course_id=record.manifest.course_id,
                        course_name=record.manifest.course_name,
                        source_name=Path(rel_path).name,
                        source_path=source_path,
                        chunk_id=f"{record.manifest.course_id}:{Path(rel_path).as_posix()}:{index}",
                        content=chunk,
                        modified_at=modified_at,
                    )
                )
    return chunks, unsupported_files, latest_source_mtime


def _score_chunk(query: str, chunk: CourseChunk) -> float:
    normalized_query = _normalize_text(query)
    query_tokens = _tokenize(query)
    haystack = _normalize_text(
        " ".join(
            [
                chunk.course_id,
                chunk.course_name,
                chunk.source_name,
                chunk.content,
            ]
        )
    )
    haystack_tokens = _tokenize(haystack)

    if not normalized_query or not query_tokens:
        return 0.0

    score = 0.0
    overlap = query_tokens & haystack_tokens
    score += len(overlap) * 2.0

    for token in query_tokens:
        if token in {chunk.course_id.lower(), chunk.course_name.lower(), chunk.source_name.lower()}:
            score += 1.0

    if normalized_query in haystack:
        score += 4.0

    if len(query_tokens) >= 2:
        query_phrases = [
            " ".join(parts)
            for parts in zip(sorted(query_tokens), sorted(query_tokens)[1:])
        ]
        if any(phrase and phrase in haystack for phrase in query_phrases):
            score += 1.5

    return score


def retrieve_course_context(
    query: str,
    *,
    courses_root: Path | None = None,
    max_hits: int = MAX_HITS,
) -> CourseRetrievalResult | None:
    records = list_course_manifests(courses_root or default_courses_root())
    if not records:
        return None

    chunks, unsupported_files, latest_source_mtime = _iter_chunks(records)
    if not chunks:
        return None

    scored_hits: list[CourseRetrievalHit] = []
    for chunk in chunks:
        score = _score_chunk(query, chunk)
        if score < MIN_RETRIEVAL_SCORE:
            continue
        scored_hits.append(
            CourseRetrievalHit(
                course_id=chunk.course_id,
                course_name=chunk.course_name,
                source_name=chunk.source_name,
                source_path=chunk.source_path,
                chunk_id=chunk.chunk_id,
                content=chunk.content,
                score=score,
                modified_at=chunk.modified_at,
            )
        )

    if not scored_hits:
        return None

    scored_hits.sort(key=lambda hit: (-hit.score, hit.course_id, hit.source_name, hit.chunk_id))
    selected_hits: list[CourseRetrievalHit] = []
    seen_sources: set[tuple[str, str]] = set()
    for hit in scored_hits:
        source_key = (hit.course_id, hit.source_name)
        if source_key in seen_sources and len(selected_hits) >= max_hits:
            continue
        selected_hits.append(hit)
        seen_sources.add(source_key)
        if len(selected_hits) >= max_hits:
            break

    top_score = selected_hits[0].score
    confidence = "low"
    if top_score >= 8:
        confidence = "high"
    elif top_score >= 4:
        confidence = "medium"

    summary = (
        f"Retrieved {len(selected_hits)} local course chunk(s) from {len(seen_sources)} source file(s) "
        f"across {len(records)} course manifest(s)."
    )
    return CourseRetrievalResult(
        query=query,
        hits=selected_hits,
        confidence=confidence,
        source_status="verified_source",
        summary=summary,
        latest_source_mtime=latest_source_mtime,
        course_count=len(records),
        source_file_count=sum(len(record.manifest.source_files) for record in records),
        indexed_chunk_count=len(chunks),
        unsupported_files=unsupported_files,
    )
