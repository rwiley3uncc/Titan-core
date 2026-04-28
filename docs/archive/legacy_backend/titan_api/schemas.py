from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    mode: Optional[str] = "personal_general"


class ChatResponse(BaseModel):
    reply: str
    proposed_actions: List[Dict[str, Any]] = Field(default_factory=list)