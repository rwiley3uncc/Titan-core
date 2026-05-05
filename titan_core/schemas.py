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
    action_id: Optional[str] = None
    created_at: Optional[float] = None
    status: str = "pending"
    confidence: Optional[float] = None
    reason: str = ""
    args: Dict[str, Any] = Field(default_factory=dict)


class ProposedPlan(BaseModel):
    plan_id: str
    created_at: float
    summary: str
    current_step_index: int = 0
    next_step_message: str = ""
    actions: List[ProposedAction] = Field(default_factory=list)


class BrainInput(BaseModel):
    user_id: int
    role: str
    mode: str = "personal_general"
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    messages: List[ChatMessage] = Field(default_factory=list)


class BrainOutput(BaseModel):
    reply: str
    proposed_actions: List[ProposedAction] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str
    mode: Optional[str] = "personal_general"
    web_enabled: Optional[bool] = False
    file_name: Optional[str] = None
    file_content: Optional[str] = None
    active_plan: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    reply: str
    proposed_actions: List[ProposedAction] = Field(default_factory=list)
    route_used: Optional[str] = None
    source_type: Optional[str] = None
    source_status: Optional[str] = None
    source_label: Optional[str] = None
    source_names: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)
    source_items: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: Optional[str] = None
    proposed_plan: Optional[ProposedPlan] = None
    replace_current_step: bool = False
    skip_current_step: bool = False
    approve_next_step: bool = False
    suggest_replace: bool = False
    target_action: Optional[str] = None
    suggestion_confidence: Optional[float] = None
    suggestion_reason: Optional[str] = None
    suggested_replacement_action: Optional[Dict[str, Any]] = None
    new_action: Optional[ProposedAction] = None


class TaskRecord(BaseModel):
    task_id: str
    title: str
    due_date: Optional[str] = None
    status: str
    priority: int = 0
    created_at: str
    updated_at: str


class CalendarSourceRecord(BaseModel):
    id: str
    name: str
    type: str
    url: str
    enabled: bool = True
    created_at: str
    updated_at: str


class CalendarSourceCreate(BaseModel):
    name: str
    type: str
    url: str
    enabled: bool = False


class CalendarSourceUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    url: Optional[str] = None
    enabled: Optional[bool] = None


class DismissedItemRecord(BaseModel):
    item_id: str
    title: str
    course: str
    dismissed_at: str
    reason: str


class DismissedItemCreate(BaseModel):
    item_id: str
    title: str
    course: str
    reason: str = "user dismissed"
