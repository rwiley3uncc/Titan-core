from __future__ import annotations

import json
from pathlib import Path

from titan_core.titan_ai_imports import enable_titan_ai_imports
from titan_core.titan_shared_imports import ensure_titan_shared_on_path

enable_titan_ai_imports()
ensure_titan_shared_on_path()

from titan_ai.prompts import build_system_prompt
from titan_ai.ai_types import AIMessage, AIRequest
from titan_core.chat_mode import is_personal_assistant_mode, safe_mode
from titan_core.course_manifest import list_course_manifests, validate_course_manifest_record
from titan_core.policy import apply_policy
from titan_core.schemas import BrainInput, BrainOutput, ChatMessage, ProposedAction
from titan_shared.runtime_validation import print_validation_report, python_runtime_summary


ROOT = Path(__file__).resolve().parent
STUDENT_MODE_CONFIG_PATH = ROOT / "configs" / "student_mode_config.json"
COURSES_ROOT = ROOT / "data" / "courses"


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
        if supported_extensions != [".md", ".txt", ".json"]:
            issues.append("student mode config must declare supported_extensions ['.md', '.txt', '.json'].")

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


def main() -> int:
    issues: list[str] = []
    details = python_runtime_summary()
    details["student_mode_config_path"] = str(STUDENT_MODE_CONFIG_PATH)
    details["courses_root"] = str(COURSES_ROOT)

    issues.extend(_validate_student_mode_config())
    issues.extend(_validate_mode_aliases())
    issues.extend(_validate_policy_behavior())
    issues.extend(_validate_prompt_behavior())
    issues.extend(_validate_course_manifests())

    return print_validation_report("Titan Student Mode Validation", issues, details)


if __name__ == "__main__":
    raise SystemExit(main())
