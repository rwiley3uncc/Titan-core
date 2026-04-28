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
import re

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
# Helper Functions
# ---------------------------------------------------------------------

MEMORY_SAVE_TRIGGERS = [
    "remember that",
    "remember this",
    "titan remember",
    "hey titan remember",
    "save this",
    "store this",
]


def normalize_text(text: str) -> str:
    """
    Lowercase, trim, and collapse whitespace.
    Keeps punctuation handling simple for MVP.
    """
    if not text:
        return ""

    text = text.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def tokenize(text: str) -> set[str]:
    """
    Small word tokenizer for keyword overlap matching.
    Filters out very short words to reduce noise.
    """
    words = re.findall(r"\w+", normalize_text(text))
    return {word for word in words if len(word) > 2}


def is_memory_save_request(user_text: str) -> bool:
    """
    Detect explicit save-memory requests.
    """
    text = normalize_text(user_text)
    return any(trigger in text for trigger in MEMORY_SAVE_TRIGGERS)


def extract_memory_content(user_text: str) -> str:
    """
    Remove the command phrase and keep only the fact itself.
    Example:
        'hey titan remember that I park in lot 5'
    becomes:
        'I park in lot 5'
    """
    if not user_text:
        return ""

    text = user_text.strip()

    patterns = [
        r"(?i)^hey titan remember that\s*",
        r"(?i)^titan remember that\s*",
        r"(?i)^remember that\s*",
        r"(?i)^hey titan remember\s*",
        r"(?i)^titan remember\s*",
        r"(?i)^remember this\s*",
        r"(?i)^save this\s*",
        r"(?i)^store this\s*",
    ]

    for pattern in patterns:
        text = re.sub(pattern, "", text).strip()

    return text


def get_or_create_memory(
    db: Session,
    user_id: int,
    tag: str,
    content: str,
    score: int = 1
) -> tuple[MemoryItem, bool]:
    """
    Prevent exact duplicate memory entries for the same user.
    Returns:
        (memory_item, created_new)
    """
    normalized_content = normalize_text(content)

    existing_rows = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user_id, MemoryItem.tag == tag)
        .order_by(MemoryItem.id.desc())
        .all()
    )

    for row in existing_rows:
        if normalize_text(row.content) == normalized_content:
            return row, False

    memory = MemoryItem(
        user_id=user_id,
        tag=tag,
        content=content,
        score=score,
    )
    db.add(memory)
    db.commit()
    db.refresh(memory)

    return memory, True


def find_memory_match(db: Session, user_id: int, user_text: str) -> MemoryItem | None:
    """
    MVP memory retrieval:
    - keyword overlap
    - prefers higher overlap
    - breaks ties by newest memory
    - returns best match even if overlap is small
    """
    query_words = tokenize(user_text)
    if not query_words:
        return None

    rows = (
        db.query(MemoryItem)
        .filter(MemoryItem.user_id == user_id)
        .order_by(MemoryItem.id.desc())
        .all()
    )

    best_row = None
    best_score = 0

    for row in rows:
        memory_words = tokenize(row.content)
        overlap = len(query_words & memory_words)

        if overlap > best_score:
            best_row = row
            best_score = overlap

    return best_row


def format_memory_reply(memory_item: MemoryItem) -> str:
    """
    Convert stored memory into a direct assistant response.
    """
    content = (memory_item.content or "").strip()
    if not content:
        return "I found a memory match, but it was empty."

    return f"You told me: {content}"


def build_brain_input(db: Session, conversation_id: int, user: User) -> BrainInput:
    """
    Build the BrainInput object from stored conversation history.
    """
    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.id.asc())
        .all()
    )

    mode_map = {
        "student": "student_coach",
        "teacher": "teacher_ta",
        "admin": "admin",
    }

    return BrainInput(
        user_id=user.id,
        role=user.role,
        mode=mode_map.get(user.role, "student_general"),
        messages=[ChatMessage(role=m.role, content=m.content) for m in msgs],
        tools=["create_task", "save_memory", "draft_email"],
    )


def write_assistant_reply(db: Session, conversation_id: int, reply_text: str) -> None:
    """
    Store assistant message in the message history.
    """
    db.add(Message(conversation_id=conversation_id, role="assistant", content=reply_text))
    db.commit()


def write_audit_log(
    db: Session,
    user_id: int,
    request_text: str,
    reply_text: str,
    proposed_actions: list
) -> AuditLog:
    """
    Store the audit record for every chat request.
    """
    audit = AuditLog(
        user_id=user_id,
        request_text=request_text,
        proposed_actions_json=json.dumps(proposed_actions),
        approved_actions_json=json.dumps([]),
        result_json=json.dumps({"reply": reply_text}),
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


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

    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Store user message
    db.add(Message(conversation_id=conversation_id, role="user", content=clean_text))
    db.commit()

    reply_text = None
    proposed_actions = []

    # 1. Explicit memory save request
    if is_memory_save_request(clean_text):
        memory_content = extract_memory_content(clean_text)

        if not memory_content:
            reply_text = "Tell me what you want me to remember."
        else:
            memory_item, created_new = get_or_create_memory(
                db=db,
                user_id=user.id,
                tag="user",
                content=memory_content,
                score=1,
            )

            if created_new:
                reply_text = f"Got it. I'll remember that: {memory_item.content}"
            else:
                reply_text = f"I already had that in memory: {memory_item.content}"

    # 2. Memory lookup before AI fallback
    if reply_text is None:
        memory_match = find_memory_match(db, user.id, clean_text)
        if memory_match:
            reply_text = format_memory_reply(memory_match)

    # 3. Fall back to brain only if memory did not answer
    if reply_text is None:
        brain_input = build_brain_input(db, conversation_id, user)

        brain_output = run_brain(
            brain_input,
            db=db,
            user_id=user.id,
        )

        reply_text = brain_output.reply
        proposed_actions = [a.model_dump() for a in brain_output.proposed_actions]

    # Store assistant reply
    write_assistant_reply(db, conversation_id, reply_text)

    # Log audit record
    audit = write_audit_log(
        db=db,
        user_id=user.id,
        request_text=clean_text,
        reply_text=reply_text,
        proposed_actions=proposed_actions,
    )

    return {
        "reply": reply_text,
        "proposed_actions": proposed_actions,
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