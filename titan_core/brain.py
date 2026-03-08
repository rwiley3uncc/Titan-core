"""
Titan Core - Cognitive Planning Engine
---------------------------------------

Purpose:
    Transforms structured conversation input (BrainInput)
    into a structured BrainOutput containing:

        - Natural language reply
        - Proposed tool actions (NOT executed here)

Role in Architecture:
    Controller  ->  Brain  ->  ProposedRun
    Brain NEVER executes actions.
    Brain ONLY proposes structured actions.

Design Philosophy:
    - Side-effect free
    - Deterministic (rule-based for MVP)
    - Future-proofed for LLM swap-in
    - Strict input/output contract

Upgrade Path:
    The body of run_brain() can later be replaced
    with an LLM call while keeping the same
    BrainInput -> BrainOutput contract.

Author:
    Ron Wiley
Project:
    Titan AI - Operational Personnel Assistant
"""

from __future__ import annotations

from typing import Optional

from .schemas import BrainInput, BrainOutput, ProposedAction
from .rules import propose_from_text

# NEW: Post-planning enforcement layers (keep Brain clean + modular)
# - policy.py enforces role rules + academic integrity constraints
# - validator.py ensures the final output is well-formed
from .policy import apply_policy
from .validator import validate_output


# ---------------------------------------------------------------------
# Core Brain Execution
# ---------------------------------------------------------------------

def run_brain(inp: BrainInput) -> BrainOutput:
    """
    Main cognitive entrypoint.

    Extracts latest user message,
    runs it through rule engine,
    then applies policy + validation,
    returns structured response.

    Parameters:
        inp (BrainInput): Structured conversation history

    Returns:
        BrainOutput: Reply + proposed actions
    """

    # -----------------------------------------------------------------
    # 1. Extract Most Recent User Message
    # -----------------------------------------------------------------

    user_text: Optional[str] = None

    for message in reversed(inp.messages):
        if message.role == "user":
            user_text = message.content
            break

    if not user_text:
        raw = BrainOutput(reply="No user input detected.", proposed_actions=[])
        # Even this goes through policy/validation for consistency.
        return validate_output(apply_policy(inp, raw))

    # -----------------------------------------------------------------
    # 2. Run Rule-Based Planner (MVP Mode)
    # -----------------------------------------------------------------

    reply, actions = propose_from_text(user_text)

    # -----------------------------------------------------------------
    # 3. Convert Raw Dict Actions -> Typed ProposedAction
    # -----------------------------------------------------------------

    structured_actions: list[ProposedAction] = []
    for action in actions:
        # Defensive conversion in case a rule emits malformed output
        a_type = action.get("type")
        a_args = action.get("args", {})

        if not isinstance(a_type, str):
            continue
        if not isinstance(a_args, dict):
            a_args = {}

        structured_actions.append(ProposedAction(type=a_type, args=a_args))

    # -----------------------------------------------------------------
    # 4. Build Raw Output (Planner Output Only)
    # -----------------------------------------------------------------

    raw_output = BrainOutput(
        reply=reply,
        proposed_actions=structured_actions
    )

    # -----------------------------------------------------------------
    # 5. Apply Policy Layer (role rules, academic integrity, tool allow-list)
    # -----------------------------------------------------------------

    policy_output = apply_policy(inp, raw_output)

    # -----------------------------------------------------------------
    # 6. Validate Final Output (structure, empty reply, malformed actions)
    # -----------------------------------------------------------------

    final_output = validate_output(policy_output)

    return final_output