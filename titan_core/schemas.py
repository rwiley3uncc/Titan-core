from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ProposedAction(BaseModel):
    type: str
    app: Optional[str] = None
    label: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class BrainInput(BaseModel):
    user_id: int
    role: str
    mode: str = "personal_general"
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    messages: List[ChatMessage] = Field(default_factory=list)


class BrainOutput(BaseModel):
    reply: str
    proposed_actions: List[Dict[str, Any]] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str
    mode: Optional[str] = "personal_general"


class ChatResponse(BaseModel):
    reply: str
    proposed_actions: List[Dict[str, Any]] = Field(default_factory=list)