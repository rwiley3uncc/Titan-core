"""
Titan Core - Output Validator
------------------------------

Ensures:
    - Reply is non-empty
    - Proposed actions are well-formed
    - Defensive cleanup to prevent bad UI/DB writes

This is NOT a policy engine.
It does not decide what is allowed.
It only enforces shape/consistency.

Why this exists:
    The brain can produce imperfect output. The validator prevents bad output
    from breaking the UI or creating malformed action objects.

Typical flow:
    brain -> validator -> policy -> (execution / simulation) -> UI
"""

from __future__ import annotations

from .schemas import BrainOutput


_MAX_REPLY_CHARS = 4000  # MVP sanity limit (adjust later)


def validate_output(out: BrainOutput) -> BrainOutput:
    """
    Defensive cleanup + basic sanity checks.

    Never throws on normal bad output; instead, it clamps/cleans.
    """
    # Ensure reply exists
    if not out.reply or not out.reply.strip():
        out.reply = "I’m not sure how to respond to that. Can you rephrase or add a little context?"

    # Clamp reply size (prevents UI overflow + audit bloat)
    if len(out.reply) > _MAX_REPLY_CHARS:
        out.reply = out.reply[:_MAX_REPLY_CHARS].rstrip() + "\n\n(Truncated for display.)"

    # Remove malformed actions
    clean = []
    for a in out.proposed_actions:
        if not getattr(a, "type", None):
            continue
        if not isinstance(a.type, str):
            continue
        if not isinstance(getattr(a, "args", None), dict):
            continue
        clean.append(a)

    out.proposed_actions = clean
    return out