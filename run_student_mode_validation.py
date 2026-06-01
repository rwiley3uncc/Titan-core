from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from titan_core.titan_ai_imports import enable_titan_ai_imports
from titan_core.titan_shared_imports import ensure_titan_shared_on_path

enable_titan_ai_imports()
ensure_titan_shared_on_path()

from titan_ai.ai_types import AIMessage, AIRequest
from titan_ai.prompts import build_system_prompt
from titan_core.chat_mode import is_personal_assistant_mode, safe_mode
from titan_core.course_manifest import list_course_manifests, validate_course_manifest_record
from titan_core.policy import apply_policy
from titan_core.schemas import BrainInput, BrainOutput, ChatMessage, ProposedAction
from titan_battlebuddy.main import app
from titan_shared.runtime_validation import print_validation_report, python_runtime_summary


ROOT = Path(__file__).resolve().parent
STUDENT_MODE_CONFIG_PATH = ROOT / "configs" / "student_mode_config.json"
COURSES_ROOT = ROOT / "data" / "courses"
EXPECTED_EXTENSIONS = [".pdf", ".md", ".txt"]


def _validate_student_mode_config() -> list[str]:
    issues: list[str] = []

    if not STUDENT_MODE_CONFIG_PATH.exists():
        return [f"Missing student mode config: {STUDENT_MODE_CONFIG_PATH}"]

    try:
        payload = json.loads(STUDENT_MODE_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"Invalid student mode config JSON: {exc}"]

    if not isinstance(payload, dict):
        return ["Student mode config must be a JSON object."]

    if str(payload.get("mode_id") or "").strip() != "student_ops":
        issues.append("student mode config must declare mode_id='student_ops'.")

    behavior_rules = payload.get("behavior_rules")
    if not isinstance(behavior_rules, dict):
        issues.append("student mode config must include a behavior_rules object.")
    else:
        required_true_flags = (
            "teach_and_explain",
            "allow_concept_guidance",
            "require_source_honesty",
            "require_missing_info_disclosure",
            "forbid_direct_graded_work_completion",
            "forbid_hidden_tool_execution",
            "forbid_autonomous_remediation",
            "forbid_live_apply",
        )
        for flag in required_true_flags:
            if behavior_rules.get(flag) is not True:
                issues.append(f"student mode config must set behavior_rules.{flag}=true.")

    source_policy = payload.get("source_policy")
    if not isinstance(source_policy, dict):
        issues.append("student mode config must include a source_policy object.")
    else:
        for flag in ("local_first", "read_only_course_materials", "cite_sources_when_available", "no_hidden_web_calls"):
            if source_policy.get(flag) is not True:
                issues.append(f"student mode config must set source_policy.{flag}=true.")

    retrieval_policy = payload.get("retrieval_policy")
    if not isinstance(retrieval_policy, dict):
        issues.append("student mode config must include a retrieval_policy object.")
    else:
        for flag in ("enabled", "local_only", "read_only"):
            if retrieval_policy.get(flag) is not True:
                issues.append(f"student mode config must set retrieval_policy.{flag}=true.")
        if retrieval_policy.get("persistent_background_indexing") is not False:
            issues.append("student mode config must set retrieval_policy.persistent_background_indexing=false.")
        supported_extensions = retrieval_policy.get("supported_extensions")
        if supported_extensions != EXPECTED_EXTENSIONS:
            issues.append(
                "student mode config must declare supported_extensions ['.pdf', '.md', '.txt']."
            )

    return issues


def _validate_mode_aliases() -> list[str]:
    issues: list[str] = []
    if safe_mode("student_ops") != "student_ops":
        issues.append("safe_mode('student_ops') did not preserve the student_ops mode.")
    if not is_personal_assistant_mode("student_ops"):
        issues.append("student_ops must route through the personal-grounded assistant path.")
    return issues


def _validate_policy_behavior() -> list[str]:
    issues: list[str] = []
    inp = BrainInput(
        user_id=1,
        role="student",
        mode="student_ops",
        messages=[ChatMessage(role="user", content="This is my quiz. Just give me the answer.")],
    )
    out = BrainOutput(
        reply="The answer is 42.",
        proposed_actions=[ProposedAction(type="draft_email", label="should be removed")],
    )
    guarded = apply_policy(inp, out)
    if "can't help with answers to an active quiz" not in guarded.reply.lower():
        issues.append("student_ops policy did not enforce the quiz/exam refusal path.")
    if guarded.proposed_actions:
        issues.append("student_ops policy should clear proposed actions during quiz/exam refusal.")
    return issues


def _validate_prompt_behavior() -> list[str]:
    issues: list[str] = []
    prompt = build_system_prompt(
        AIRequest(
            role="student",
            mode="student_ops",
            tools=[],
            messages=[AIMessage(role="user", content="Help me study.")],
        )
    ).lower()
    for marker in (
        "student operations assistant",
        "do not directly complete graded work",
        "use only verified source context",
        "do not perform hidden tool use",
        "name the course/source files you relied on",
    ):
        if marker not in prompt:
            issues.append(f"student_ops prompt is missing required guidance marker: {marker}")
    return issues


def _validate_course_manifests() -> list[str]:
    issues: list[str] = []
    if not COURSES_ROOT.exists():
        return [f"Missing courses root: {COURSES_ROOT}"]

    for record in list_course_manifests(COURSES_ROOT):
        issues.extend(validate_course_manifest_record(record))

    return issues


def _validation_detail(response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, dict):
            return str(detail.get("message") or detail.get("status") or payload)
        if detail is not None:
            return str(detail)
    return str(payload)


def _validate_battlebuddy_student_documents() -> list[str]:
    issues: list[str] = []
    temp_root = Path(tempfile.mkdtemp(prefix="titan-student-mode-validation-"))
    docs_root = temp_root / "course_documents"
    previous_docs_root = os.environ.get("TITAN_COURSE_DOCUMENTS_DIR")
    os.environ["TITAN_COURSE_DOCUMENTS_DIR"] = str(docs_root)

    try:
        with TestClient(app) as client:
            seed_response = client.post("/seed")
            if seed_response.status_code != 200:
                issues.append(
                    f"BattleBuddy seed endpoint returned HTTP {seed_response.status_code}: {_validation_detail(seed_response)}"
                )
                return issues

            upload_response = client.post(
                "/api/student-documents/upload",
                data={
                    "course_tag": "NET-301",
                    "document_category": "lecture_notes",
                },
                files={
                    "file": (
                        "net301_notes.md",
                        (
                            "# NET-301 Notes\n"
                            "Subnetting practice labs are required every week.\n"
                            "Bring your calculator to the subnetting lab review.\n"
                        ).encode("utf-8"),
                        "text/markdown",
                    )
                },
            )
            if upload_response.status_code != 200:
                issues.append(
                    f"BattleBuddy student document upload endpoint returned HTTP {upload_response.status_code}: {_validation_detail(upload_response)}"
                )
                return issues

            upload_payload = upload_response.json()
            record = upload_payload.get("record")
            if not isinstance(record, dict):
                issues.append("BattleBuddy student document upload endpoint did not return a structured document record.")
                return issues
            if str(record.get("course_tag") or "") != "NET-301":
                issues.append("BattleBuddy student document upload endpoint did not preserve the uploaded course tag.")
            if str(record.get("document_category") or "") != "lecture_notes":
                issues.append("BattleBuddy student document upload endpoint did not preserve the uploaded document category.")
            stored_source_path = Path(str(record.get("source_path") or ""))
            if not stored_source_path.exists():
                issues.append("BattleBuddy student document upload endpoint did not store the selected file locally.")
            elif docs_root not in stored_source_path.parents and stored_source_path != docs_root:
                issues.append("BattleBuddy student document upload stored the file outside the allowlisted local course document workspace.")

            list_response = client.get("/api/student-documents?limit=5")
            if list_response.status_code != 200:
                issues.append(
                    f"BattleBuddy student document listing endpoint returned HTTP {list_response.status_code}: {_validation_detail(list_response)}"
                )
                return issues
            list_payload = list_response.json()
            documents = list_payload.get("documents")
            if not isinstance(documents, list) or not documents:
                issues.append("BattleBuddy student document listing endpoint did not return the ingested file.")

            unsupported_response = client.post(
                "/api/student-documents/upload",
                data={
                    "course_tag": "NET-301",
                    "document_category": "lecture_notes",
                },
                files={
                    "file": (
                        "net301_notes.docx",
                        b"placeholder docx bytes",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )
            if unsupported_response.status_code != 400:
                issues.append(
                    f"BattleBuddy student document upload endpoint did not reject unsupported DOCX input safely (HTTP {unsupported_response.status_code})."
                )
            elif "pdf, txt, and md" not in _validation_detail(unsupported_response).lower():
                issues.append("BattleBuddy student document upload rejection for unsupported DOCX input was not explicit enough.")

            grounded_chat_response = client.post(
                "/api/chat",
                json={
                    "message": "What do my uploaded notes say about subnetting practice?",
                    "mode": "student_ops",
                    "web_enabled": True,
                },
            )
            if grounded_chat_response.status_code != 200:
                issues.append(
                    f"BattleBuddy student grounded chat path returned HTTP {grounded_chat_response.status_code}: {_validation_detail(grounded_chat_response)}"
                )
                return issues
            grounded_payload = grounded_chat_response.json()
            if str(grounded_payload.get("source_label") or "") != "Source: Local Course Material":
                issues.append("BattleBuddy student grounded chat response did not identify the local course material source label.")
            reply_text = str(grounded_payload.get("reply") or "")
            if "Grounded sources:" not in reply_text or "chunk" not in reply_text.lower():
                issues.append("BattleBuddy student grounded chat response did not cite retrieved document chunks in the answer text.")
            source_items = grounded_payload.get("source_items")
            if not isinstance(source_items, list) or not source_items:
                issues.append("BattleBuddy student grounded chat response did not attach structured evidence items.")

            insufficient_response = client.post(
                "/api/chat",
                json={
                    "message": "What do my uploaded notes say about interstellar llama harmonics and quaternion pastry theorems?",
                    "mode": "student_ops",
                    "web_enabled": True,
                },
            )
            if insufficient_response.status_code != 200:
                issues.append(
                    f"BattleBuddy insufficient-evidence student chat path returned HTTP {insufficient_response.status_code}: {_validation_detail(insufficient_response)}"
                )
                return issues
            insufficient_payload = insufficient_response.json()
            insufficient_reply = str(insufficient_payload.get("reply") or "").lower()
            source_status = str(insufficient_payload.get("source_status") or "").strip().lower()
            source_items = insufficient_payload.get("source_items")
            if not insufficient_reply:
                issues.append("BattleBuddy student chat path did not report insufficient evidence clearly when no grounded support existed.")
            elif source_status not in {"verified_source", "missing_verified_source", "insufficient_evidence"}:
                issues.append("BattleBuddy student chat path returned an unexpected source status for the unsupported grounded query.")
            elif not isinstance(source_items, list):
                issues.append("BattleBuddy student chat path did not return a structured source_items list for the unsupported grounded query.")

            combined_response = client.post(
                "/api/chat",
                json={
                    "message": "When is my next class and what do my uploaded notes say about subnetting practice?",
                    "mode": "student_ops",
                    "web_enabled": False,
                },
            )
            if combined_response.status_code != 200:
                issues.append(
                    f"BattleBuddy combined student document and calendar chat path returned HTTP {combined_response.status_code}: {_validation_detail(combined_response)}"
                )
                return issues
            combined_payload = combined_response.json()
            if str(combined_payload.get("source_label") or "") != "Source: Local Course Material + Sitrep / Dashboard":
                issues.append("BattleBuddy combined student document and calendar answer did not preserve the read-only mixed-source label.")
            combined_reply = str(combined_payload.get("reply") or "")
            if "Read-only calendar context:" not in combined_reply:
                issues.append("BattleBuddy combined student answer did not expose calendar context as read-only.")
            if combined_payload.get("proposed_actions"):
                issues.append("BattleBuddy combined student answer should not add autonomous actions while presenting read-only calendar context.")
    finally:
        if previous_docs_root is None:
            os.environ.pop("TITAN_COURSE_DOCUMENTS_DIR", None)
        else:
            os.environ["TITAN_COURSE_DOCUMENTS_DIR"] = previous_docs_root

    return issues


def main() -> int:
    issues: list[str] = []
    details = python_runtime_summary()
    details["student_mode_config_path"] = str(STUDENT_MODE_CONFIG_PATH)
    details["courses_root"] = str(COURSES_ROOT)
    details["expected_supported_extensions"] = EXPECTED_EXTENSIONS

    issues.extend(_validate_student_mode_config())
    issues.extend(_validate_mode_aliases())
    issues.extend(_validate_policy_behavior())
    issues.extend(_validate_prompt_behavior())
    issues.extend(_validate_course_manifests())
    issues.extend(_validate_battlebuddy_student_documents())

    return print_validation_report("Titan Student Mode Validation", issues, details)


if __name__ == "__main__":
    raise SystemExit(main())
