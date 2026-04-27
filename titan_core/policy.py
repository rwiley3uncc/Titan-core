"""
Titan Core - Policy Engine (Mode-Aware, University-Ready)
---------------------------------------------------------

Goal:
  Make Titan useful for students (study guidance, learning, university info)
  while preventing academic integrity violations (no direct answers on graded work).

Key behaviors:
  - student_coach:
      * If quiz/exam/test/graded context -> NO direct answers. Offer concept review,
        study plan, and similar-but-not-same practice problems.
      * If answer-seeking WITHOUT exam context -> coach (Socratic), guide steps,
        check work, hints. Avoid dumping final answers.
      * If user is asking general knowledge or university info -> answer normally.
  - teacher_ta:
      * More direct assistance allowed (still future-proof for FERPA/exam policies).
  - admin:
      * Unrestricted (for internal testing).

Design:
  - Pure function (no side effects)
  - Heuristic MVP rules; upgrade later to classifier/LLM-judge if desired.

Author:
  Ron Wiley
Project:
  Titan AI - Operational Personnel Assistant
"""

from __future__ import annotations

import re
from typing import Iterable

from .schemas import BrainInput, BrainOutput


# ---------------------------------------------------------------------
# Tool allow-lists (tight by design; expand intentionally)
# ---------------------------------------------------------------------

_ALLOWED_TOOLS_BY_MODE = {
    "personal_general": {"create_task", "save_memory", "draft_email"},
    "personal_productivity": {"create_task", "save_memory", "draft_email"},
    "personal_builder": {"create_task", "save_memory", "draft_email"},
    "personal_family": {"create_task", "save_memory", "draft_email"},
    "development_assistant": {"create_task", "save_memory", "draft_email"},
    "student_coach": {"create_task", "save_memory", "draft_email"},
    "student_general": {"create_task", "save_memory", "draft_email"},
    "teacher_ta": {"create_task", "save_memory", "draft_email"},
    "admin": {"create_task", "save_memory", "draft_email"},
}


# ---------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------

# Strong integrity triggers (graded / active assessment context)
_EXAM_INTEGRITY_PATTERNS = [
    r"\bquiz\b",
    r"\bexam\b",
    r"\bmidterm\b",
    r"\bfinal\b",
    r"\btest\b",            # IMPORTANT: you hit this gap already
    r"\bassessment\b",
    r"\bgraded\b",
    r"\btimed\b",
    r"\bproctored\b",
    r"\blockdown\b",
    r"\brespondus\b",
    r"\bhonorlock\b",
    r"\bopen\s*book\b",
    r"\bopen\s*note\b",
]

# Answer-seeking / do-my-work language
_STUDENT_ANSWER_SEEKING_PATTERNS = [
    r"\bjust\s+give\s+me\s+the\s+answer\b",
    r"\bwhat(?:'s|\s+is)\s+the\s+answer\b",
    r"\b(answer|solution)\s*(?:to|for)\b",
    r"\bsolve\s+this\b",
    r"\bdo\s+my\s+homework\b",
    r"\bgive\s+me\s+the\s+solution\b",
    r"\bgive\s+me\s+the\s+final\b",
    r"\bfinal\s+answer\b",
    r"\bcorrect\s+answer\b",
    r"\bis\s+it\s+\d+(\.\d+)?\s*\??\b",
    r"\bwhat\s+do\s+i\s+put\b",
    r"\bwhat\s+should\s+i\s+write\b",
]

# If assistant reply looks like it leaked a direct answer
_ASSISTANT_ANSWER_LEAK_PATTERNS = [
    r"\bthe\s+answer\s+is\b",
    r"\bfinal\s+answer\b",
    r"^\s*[-+]?\d+(\.\d+)?\s*$",   # reply is just a number
    r"^\s*[A-D]\s*$",              # reply is just MC choice
    r"\bsolution:\b",
    r"\bhere(?:'s|\s+is)\s+the\s+solution\b",
]

# Signals user is asking for learning support (allowed)
_LEARNING_INTENT_HINTS = [
    r"\bexplain\b",
    r"\bhelp\s+me\s+understand\b",
    r"\bwalk\s+me\s+through\b",
    r"\bstep\s+by\s+step\b",
    r"\bhint\b",
    r"\bcheck\s+my\s+work\b",
    r"\bwhat\s+did\s+i\s+do\s+wrong\b",
    r"\bhow\s+do\s+i\b",
    r"\bwhy\b",
    r"\bconcept\b",
    r"\bstudy\b",
    r"\bpractice\b",
]

# University / general info intent (allowed to answer normally)
_UNIVERSITY_INFO_HINTS = [
    r"\buncc\b",
    r"\bunc\s+charlotte\b",
    r"\bcampus\b",
    r"\bregistrar\b",
    r"\badvis(?:or|ing)\b",
    r"\bfinancial\s+aid\b",
    r"\bfa\b",
    r"\bbursar\b",
    r"\btuition\b",
    r"\bdeadline\b",
    r"\badd\/drop\b",
    r"\bwithdraw\b",
    r"\bsyllabus\b",
    r"\boffice\s+hours\b",
    r"\bclass\b",
    r"\bsection\b",
    r"\bcanvas\b",
    r"\blms\b",
    r"\bschedule\b",
    r"\bcalendar\b",
    r"\bemail\b",
    r"\bprofessor\b",
    r"\binstructor\b",
    r"\bdepartment\b",
]

# Homework-like signals (not definitive, but useful)
_HOMEWORK_LIKE_HINTS = [
    r"\bproblem\s+\d+\b",
    r"\bquestion\s+\d+\b",
    r"\bworksheet\b",
    r"\bhomework\b",
    r"\bassignment\b",
    r"\blab\b",
    r"\bquiz\s+\d+\b",
    r"\bchapter\b",
    r"\bsection\b",
    r"\bpage\b",
]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    if not text:
        return False
    return any(re.search(p, text, flags=re.IGNORECASE | re.MULTILINE) for p in patterns)


def _latest_user_text(inp: BrainInput) -> str:
    for m in reversed(inp.messages):
        if m.role == "user":
            return (m.content or "").strip()
    return ""


def _infer_mode(inp: BrainInput) -> str:
    # Backward-compatible: if mode missing, infer from role
    if getattr(inp, "mode", None):
        return inp.mode  # type: ignore[return-value]
    if inp.role == "student":
        return "student_coach"
    if inp.role == "teacher":
        return "teacher_ta"
    return "admin"


def _study_coach_reply(user_text: str) -> str:
    return (
        "I can’t give a direct final answer, but I *can* help you learn it and get it right.\n\n"
        "To help you fast, pick one:\n"
        "1) **Hint** (small nudge)\n"
        "2) **Step-by-step plan** (you do each step; I check)\n"
        "3) **Check my work** (paste your attempt)\n\n"
        "Now send:\n"
        "- The exact problem statement (paste it)\n"
        "- What you tried so far (even if it’s messy)\n"
        "- Where you got stuck"
    )


def _exam_safe_reply() -> str:
    return (
        "I can’t help with answers to an active quiz/test/exam. But I *can* help you learn the concept.\n\n"
        "Here are safe options:\n"
        "- **Concept review**: tell me the topic (chapter/section) and what’s confusing.\n"
        "- **Study plan**: how much time do you have before it’s due?\n"
        "- **Similar practice**: I can generate a *similar but not the same* practice problem and walk you through it.\n\n"
        "Send:\n"
        "- The topic (not the exact graded question), and\n"
        "- What you already know vs what’s unclear."
    )


def _university_info_ok(user_text: str) -> bool:
    # If they’re clearly asking university/admin info, answer normally.
    return _matches_any(user_text, _UNIVERSITY_INFO_HINTS)


def _learning_intent(user_text: str) -> bool:
    return _matches_any(user_text, _LEARNING_INTENT_HINTS)


def _is_answer_seeking(user_text: str) -> bool:
    return _matches_any(user_text, _STUDENT_ANSWER_SEEKING_PATTERNS)


def _is_exam_context(user_text: str) -> bool:
    return _matches_any(user_text, _EXAM_INTEGRITY_PATTERNS)


def _looks_like_homework(user_text: str) -> bool:
    return _matches_any(user_text, _HOMEWORK_LIKE_HINTS)


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def apply_policy(inp: BrainInput, out: BrainOutput) -> BrainOutput:
    """
    Enforce role/mode policies on BrainOutput.
    """
    mode = _infer_mode(inp)

    # 1) Tool allow-list by mode
    allowed = _ALLOWED_TOOLS_BY_MODE.get(mode, set())
    out.proposed_actions = [a for a in out.proposed_actions if a.type in allowed]

    # 2) Student coaching behavior
    if mode == "student_coach":
        user_text = _latest_user_text(inp)

        # (A) University info / general knowledge is allowed
        # If they are asking about the university, policies, deadlines, email help, etc.,
        # we should not block them. Let the Brain answer normally.
        if _university_info_ok(user_text):
            return out

        # (B) Exam/quiz/test context: strict safe response
        if _is_exam_context(user_text):
            out.reply = _exam_safe_reply()
            out.proposed_actions = []
            return out

        # (C) If user is trying to get the answer (especially homework-like),
        # force coaching. We still provide help, but not final answers.
        if _is_answer_seeking(user_text) or (_looks_like_homework(user_text) and not _learning_intent(user_text)):
            out.reply = _study_coach_reply(user_text)
            out.proposed_actions = []
            return out

        # (D) If assistant reply leaked an answer, override to coaching
        if _matches_any(out.reply, _ASSISTANT_ANSWER_LEAK_PATTERNS):
            out.reply = _study_coach_reply(user_text)
            out.proposed_actions = []
            return out

        # (E) Otherwise: allow normal helpful guidance.
        # Student asked in a learning-oriented way -> allow the Brain’s output.
        return out

    # 3) Teacher TA mode (MVP)
    # Later you can add:
    #   - FERPA constraints
    #   - exam integrity constraints for teacher content generation
    return out
