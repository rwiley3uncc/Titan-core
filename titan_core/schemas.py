"""
Titan Core - Data Schemas
-------------------------

Purpose:
    Defines all structured data contracts used by the Brain layer.

Author:
    Ron Wiley
Project:
    Titan AI - Operational Personnel Assistant
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Any, Optional


# ---------------------------------------------------------------------
# Role / Mode Definitions
# ---------------------------------------------------------------------

Role = Literal["student", "teacher", "admin"]
MsgRole = Literal["user", "assistant", "system"]

# The key upgrade: explicit operating modes (demo-friendly + deterministic)
Mode = Literal["student_coach", "student_general", "teacher_ta", "admin"]


# ---------------------------------------------------------------------
# Message Schema
# ---------------------------------------------------------------------

class ChatMessage(BaseModel):
    """
    Single message in conversation history.
    """
    role: MsgRole
    content: str


# ---------------------------------------------------------------------
# Brain Input Schema
# ---------------------------------------------------------------------

class BrainInput(BaseModel):
    """
    Structured input to the Brain.
    """
    user_id: int
    role: Role

    # NEW:
    # If omitted, we’ll infer from role in policy (backward compatible)
    mode: Optional[Mode] = None

    messages: List[ChatMessage]
    tools: List[str]


# ---------------------------------------------------------------------
# Proposed Tool Action Schema
# ---------------------------------------------------------------------

class ProposedAction(BaseModel):
    """
    Represents a tool action proposed by the Brain.
    Execution happens elsewhere.
    """
    type: str
    args: Dict[str, Any]


# ---------------------------------------------------------------------
# Brain Output Schema
# ---------------------------------------------------------------------

class BrainOutput(BaseModel):
    """
    Structured output from the Brain.
    """
    reply: str
    proposed_actions: List[ProposedAction] = Field(default_factory=list)