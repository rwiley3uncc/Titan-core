from __future__ import annotations

from pathlib import Path

from titan_core.titan_shared_imports import ensure_titan_shared_on_path

ensure_titan_shared_on_path()

from titan_core.course_manifest import list_course_manifests, validate_course_manifest_record
from titan_core.course_retrieval import retrieve_course_context
from titan_shared.runtime_validation import print_validation_report, python_runtime_summary


ROOT = Path(__file__).resolve().parent
COURSES_ROOT = ROOT / "data" / "courses"


def main() -> int:
    issues: list[str] = []
    details = python_runtime_summary()
    details["courses_root"] = str(COURSES_ROOT)

    manifests = list_course_manifests(COURSES_ROOT)
    details["course_manifest_count"] = len(manifests)
    if not manifests:
        issues.append(f"No course manifests found under {COURSES_ROOT}.")

    for record in manifests:
        issues.extend(validate_course_manifest_record(record))

    retrieval = retrieve_course_context("What do my networking notes say about subnetting?", courses_root=COURSES_ROOT)
    if retrieval is None:
        issues.append("Local course retrieval did not return grounded results for the example subnetting query.")
    else:
        details["retrieval_course_count"] = retrieval.course_count
        details["retrieval_source_file_count"] = retrieval.source_file_count
        details["retrieval_indexed_chunk_count"] = retrieval.indexed_chunk_count
        details["retrieval_confidence"] = retrieval.confidence
        details["retrieval_latest_source_mtime"] = retrieval.latest_source_mtime
        details["retrieval_hit_count"] = len(retrieval.hits)
        details["retrieval_source_names"] = retrieval.names
        if not retrieval.hits:
            issues.append("Local course retrieval returned an empty hit list.")
        if not retrieval.names:
            issues.append("Local course retrieval did not expose source names.")
        if "subnetting" not in retrieval.context_text.lower():
            issues.append("Local course retrieval context did not include the expected subnetting material.")
        if retrieval.unsupported_files:
            issues.append(f"Local course retrieval found unsupported course files: {retrieval.unsupported_files}")

    return print_validation_report("Titan Local Course Retrieval Validation", issues, details)


if __name__ == "__main__":
    raise SystemExit(main())
