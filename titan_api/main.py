"""
Titan Core - Application Entrypoint (Laptop MVP)
------------------------------------------------

Purpose:
    Full FastAPI backend for Titan Core MVP.

Architecture Flow:
    User -> Auth -> Conversation -> Brain -> Audit
         -> Approval -> Dispatcher -> Database

Responsibilities:
    - Authentication (login, seed)
    - Conversation management
    - Brain orchestration
    - Audit logging
    - Action approval + execution
    - Data retrieval endpoints

Security Notes:
    - JWT-based authentication
    - All protected endpoints require current_user
    - Actions must be explicitly approved before execution

Author:
    Ron Wiley
Project:
    Titan AI - Operational Personnel Assistant
"""

import json

from fastapi import FastAPI, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import User, Conversation, Message, Task, MemoryItem, AuditLog, Draft
from .auth import hash_password, verify_password, create_access_token, get_current_user
from .dispatcher import execute_action

from titan_core.schemas import BrainInput, ChatMessage
from titan_core.brain import run_brain


# ---------------------------------------------------------------------
# App Initialization
# ---------------------------------------------------------------------

app = FastAPI(title="Titan Core (Laptop MVP)")

# Create tables on startup (MVP convenience)
Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------
# Static UI
# ---------------------------------------------------------------------

app.mount("/ui", StaticFiles(directory="titan_ui", html=True), name="ui")


@app.get("/", response_class=HTMLResponse)
def root():
    """Redirect root to UI."""
    return '<meta http-equiv="refresh" content="0; url=/ui/index.html">'


# ---------------------------------------------------------------------
# Seed Endpoint (Development Only)
# ---------------------------------------------------------------------

@app.post("/seed")
def seed(db: Session = Depends(get_db)):
    """
    Creates initial users for local testing.
    """
    if db.query(User).count() > 0:
        return {"ok": True, "note": "already seeded"}

    users = [
        User(username="ron", password_hash=hash_password("ronpass"), role="admin"),
        User(username="student1", password_hash=hash_password("studentpass"), role="student"),
        User(username="teacher1", password_hash=hash_password("teacherpass"), role="teacher"),
    ]

    db.add_all(users)
    db.commit()

    return {"ok": True, "created": [u.username for u in users]}


# ---------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------

@app.post("/login")
def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Bad credentials")

    return {
        "token": create_access_token(user),
        "role": user.role,
        "username": user.username
    }


# ---------------------------------------------------------------------
# Conversation Management
# ---------------------------------------------------------------------

@app.post("/conversations")
def new_conversation(
    title: str = Form("New chat"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conversation = Conversation(user_id=user.id, title=title)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    return {"id": conversation.id, "title": conversation.title}


@app.get("/conversations")
def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.id.desc())
        .all()
    )

    return [{"id": r.id, "title": r.title} for r in rows]


@app.get("/conversations/{cid}/messages")
def get_messages(
    cid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == cid, Conversation.user_id == user.id)
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == cid)
        .order_by(Message.id.asc())
        .all()
    )

    return [{"role": m.role, "content": m.content} for m in messages]


# ---------------------------------------------------------------------
# Chat Endpoint (Brain Integration)
# ---------------------------------------------------------------------

@app.post("/chat")
def chat(
    conversation_id: int = Form(...),
    text: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conversation = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
        .first()
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Store user message
    db.add(Message(conversation_id=conversation_id, role="user", content=text))
    db.commit()

    # Build BrainInput from convo history
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id.asc())
        .all()
    )

    # NEW: Explicit operating mode (drives policy behavior)
    mode_map = {
        "student": "student_coach",
        "teacher": "teacher_ta",
        "admin": "admin",
    }

    brain_input = BrainInput(
        user_id=user.id,
        role=user.role,
        mode=mode_map.get(user.role, "student_general"),
        messages=[ChatMessage(role=m.role, content=m.content) for m in msgs],
        tools=["create_task", "save_memory", "draft_email"],
    )

    brain_output = run_brain(brain_input)

    # Store assistant reply
    db.add(Message(conversation_id=conversation_id, role="assistant", content=brain_output.reply))
    db.commit()

    # Log audit record (proposal only)
    audit = AuditLog(
        user_id=user.id,
        request_text=text,
        proposed_actions_json=json.dumps([a.model_dump() for a in brain_output.proposed_actions]),
        approved_actions_json=json.dumps([]),
        result_json=json.dumps({"reply": brain_output.reply}),
    )

    db.add(audit)
    db.commit()

    return {
        "reply": brain_output.reply,
        "proposed_actions": [a.model_dump() for a in brain_output.proposed_actions],
        "audit_log_id": audit.id
    }


# ---------------------------------------------------------------------
# Action Approval + Execution
# ---------------------------------------------------------------------

@app.post("/actions/approve")
def approve(
    audit_log_id: int = Form(...),
    actions_json: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.id == audit_log_id, AuditLog.user_id == user.id)
        .first()
    )

    if not audit:
        raise HTTPException(status_code=404, detail="Audit log not found")

    actions = json.loads(actions_json)
    results = [execute_action(db, user.id, action) for action in actions]

    audit.approved_actions_json = json.dumps(actions)
    audit.result_json = json.dumps({"results": results})
    db.commit()

    return {"ok": True, "results": results}


# ---------------------------------------------------------------------
# Retrieval Endpoints
# ---------------------------------------------------------------------

@app.get("/tasks")
def tasks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rows = (
        db.query(Task)
        .filter(Task.user_id == user.id)
        .order_by(Task.id.desc())
        .all()
    )

    return [{"id": r.id, "title": r.title, "due_at": r.due_at, "status": r.status} for r in rows]


@app.get("/memory")
def memory(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rows = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user.id)
        .order_by(MemoryItem.id.desc())
        .all()
    )

    return [{"id": r.id, "tag": r.tag, "content": r.content, "score": r.score} for r in rows]


@app.get("/drafts")
def drafts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rows = (
        db.query(Draft)
        .filter(Draft.user_id == user.id)
        .order_by(Draft.id.desc())
        .all()
    )

    return [{"id": r.id, "kind": r.kind, "content": r.content} for r in rows]


@app.get("/audit")
def audit(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == user.id)
        .order_by(AuditLog.id.desc())
        .limit(50)
        .all()
    )

    return [{
        "id": r.id,
        "request_text": r.request_text,
        "proposed_actions_json": r.proposed_actions_json,
        "approved_actions_json": r.approved_actions_json,
        "result_json": r.result_json,
        "created_at": r.created_at.isoformat()
    } for r in rows]