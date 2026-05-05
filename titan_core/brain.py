"""
Titan Core - Cognitive Planning Engine
--------------------------------------

Purpose:
    Converts structured BrainInput into BrainOutput.

Design Goals:
    - Titan behaves as a personal assistant for its owner
    - Brain generates replies and proposes actions
    - Brain never executes actions
    - Memory reading allowed, writing handled in controller
"""

from __future__ import annotations

import os
from typing import Optional, Any
from sqlalchemy.orm import Session

from .schemas import BrainInput, BrainOutput, ProposedAction
from .rules import propose_from_text
from .policy import apply_policy
from .validator import validate_output
from .memory import get_recent_memories
from titan_brain.local_llm import generate_local_reply


# Kept for backward compatibility with existing configuration, but Titan's
# normal local reply path now uses Ollama instead of OpenAI.
DEFAULT_MODEL = os.getenv("TITAN_OPENAI_MODEL", "gpt-4.1-mini")
MAX_HISTORY_MESSAGES = 10
MAX_MEMORY_ITEMS = 10


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _latest_user_text(inp: BrainInput) -> Optional[str]:
    for message in reversed(inp.messages):
        if message.role == "user":
            text = (message.content or "").strip()
            if text:
                return text
    return None


def _conversation_window(inp: BrainInput) -> str:
    msgs = inp.messages[-MAX_HISTORY_MESSAGES:]
    lines = []

    for m in msgs:
        role = m.role.upper()
        content = (m.content or "").strip()
        if content:
            lines.append(f"{role}: {content}")

    return "\n".join(lines)


def _system_prompt(inp: BrainInput) -> str:
    """
    Titan mode-aware assistant prompt.
    """
    mode = inp.mode or "personal_general"
    tools = ", ".join(inp.tools) if inp.tools else "none"

    base_prompt = f"""
You are Titan, a local AI assistant.

Behavior principles:
- Be clear, calm, and practical.
- Prefer concise and structured replies.
- Suggest next steps when helpful.
- Never claim to have executed actions.
- Never invent tool results.
- Never pretend you edited files, ran code, or changed a project unless an approved tool or action actually did it.

Context:
Owner role: {inp.role}
Assistant mode: {mode}
Available tools: {tools}
"""

    if mode == "development_assistant":
        return f"""
{base_prompt}

You are operating as a local coding and project assistant.

Primary responsibilities:
- explain code clearly and accurately
- help with debugging and root-cause analysis
- suggest file-level changes and implementation steps
- offer architecture and project-structure advice
- prefer safe, reversible project changes
- ask before destructive actions or risky changes

When helping with development work:
- be explicit about which files or modules may need changes
- separate observations, likely causes, and suggested fixes when useful
- avoid claiming tests passed unless they actually ran
- avoid pretending repository or filesystem changes already happened
- use only the current development question, attached file content, and directly relevant development context
- do not mention personal reminders, sitrep data, schedules, school tasks, or unrelated personal memory unless the user explicitly asks for that

Only produce the assistant's natural language reply.
Do not produce JSON.
Do not output tool calls.
""".strip()

    return f"""
{base_prompt}

You are operating as a personal assistant for everyday local use.

Primary responsibilities:
- remembering important information
- organizing tasks, calendars, reminders, and plans
- drafting messages
- helping structure decisions
- providing practical sitrep-style summaries when helpful
- for knowledge questions, use only verified source context included in the conversation
- if the verified source context is missing or insufficient, say you do not have enough verified information

Only produce the assistant's natural language reply.
Do not produce JSON.
Do not output tool calls.
""".strip()


def _memory_context(memories: list[Any]) -> str:
    if not memories:
        return "No stored memories."

    lines = []
    for m in memories:
        tag = getattr(m, "tag", "general")
        content = getattr(m, "content", "")
        lines.append(f"- [{tag}] {content}")

    return "\n".join(lines)


def _generate_llm_reply(
    inp: BrainInput,
    user_text: str,
    memories: list[Any]
) -> Optional[str]:
    transcript = _conversation_window(inp)
    memory_block = _memory_context(memories)

    prompt = f"""
Conversation:
{transcript}

Known information:
{memory_block}

Latest message:
{user_text}

Write Titan's reply.
"""

    try:
        # Titan now uses a local Ollama backend for reply generation, while
        # memory retrieval, policy enforcement, validation, and action
        # proposal continue through the existing architecture.
        # Future model routing can happen here if modes need different local
        # backends, for example personal mode -> llama3 and development mode
        # -> a coding-focused model such as deepseek-coder.
        text = generate_local_reply(
            prompt=prompt,
            system_prompt=_system_prompt(inp)
        )

        if not text:
            return None

        return text.strip()

    except Exception:
        return None


def _convert_actions(actions: list[dict]) -> list[ProposedAction]:

    out: list[ProposedAction] = []

    for action in actions:
        a_type = action.get("type")
        a_app = action.get("app")
        a_label = action.get("label")
        a_args = action.get("args", {})

        if isinstance(a_type, str):
            out.append(
                ProposedAction(
                    type=a_type.strip(),
                    app=a_app.strip() if isinstance(a_app, str) else None,
                    label=a_label.strip() if isinstance(a_label, str) else None,
                    args=a_args if isinstance(a_args, dict) else {}
                )
            )

    return out


# ---------------------------------------------------------------------
# Core Brain Execution
# ---------------------------------------------------------------------

def run_brain(
    inp: BrainInput,
    db: Optional[Session] = None,
    user_id: Optional[int] = None
) -> BrainOutput:

    user_text = _latest_user_text(inp)

    if not user_text:
        raw = BrainOutput(reply="No user input detected.", proposed_actions=[])
        return validate_output(apply_policy(inp, raw))

    # -------------------------------------------------------------
    # Memory Retrieval
    # -------------------------------------------------------------

    memories: list[Any] = []

    if inp.mode != "development_assistant" and db is not None and user_id is not None:
        try:
            memories = get_recent_memories(db, user_id, limit=MAX_MEMORY_ITEMS)
        except Exception:
            memories = []

    # -------------------------------------------------------------
    # Deterministic Rule Actions
    # -------------------------------------------------------------

    fallback_reply, raw_actions = propose_from_text(user_text)
    structured_actions = _convert_actions(raw_actions)

    # -------------------------------------------------------------
    # LLM Reply
    # -------------------------------------------------------------

    llm_reply = _generate_llm_reply(inp, user_text, memories)

    reply = llm_reply if llm_reply else fallback_reply

    # -------------------------------------------------------------
    # Build Output
    # -------------------------------------------------------------

    raw_output = BrainOutput(
        reply=reply,
        proposed_actions=structured_actions,
    )

    policy_output = apply_policy(inp, raw_output)

    return validate_output(policy_output)
