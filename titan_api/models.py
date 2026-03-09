"""
Titan Core - Database Models
----------------------------

Purpose:
    Defines all persistent entities for Titan Core.

Design Principles:
    - Titan is a personal assistant owned by one primary user
    - All stored data belongs to the owner
    - Conversations store message history
    - Memory stores persistent facts
    - Tasks track things the owner wants to do
    - Drafts store generated text artifacts
    - Audit log records proposed and executed actions
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from .db import Base


# ---------------------------------------------------------------------
# User (Owner of Titan)
# ---------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(String(64), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    # Titan is owned by a single primary user
    role = Column(String(16), default="owner")

    created_at = Column(DateTime, default=datetime.utcnow)

    conversations = relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete"
    )

    tasks = relationship(
        "Task",
        back_populates="user",
        cascade="all, delete"
    )

    memory_items = relationship(
        "MemoryItem",
        back_populates="user",
        cascade="all, delete"
    )

    drafts = relationship(
        "Draft",
        back_populates="user",
        cascade="all, delete"
    )

    audits = relationship(
        "AuditLog",
        back_populates="user",
        cascade="all, delete"
    )


# ---------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)

    title = Column(String(120), default="New chat")

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversations")

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete"
    )


# ---------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    conversation_id = Column(Integer, ForeignKey("conversations.id"), index=True, nullable=False)

    role = Column(String(16), nullable=False)  # user | assistant | system

    content = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


# ---------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)

    title = Column(String(255), nullable=False)

    due_at = Column(String(40), nullable=True)  # ISO-8601 string

    status = Column(String(16), default="open")  # open | done

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="tasks")


# ---------------------------------------------------------------------
# Memory Item
# ---------------------------------------------------------------------

class MemoryItem(Base):
    __tablename__ = "memory_items"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)

    tag = Column(String(64), default="general")

    content = Column(Text, nullable=False)

    score = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="memory_items")


# ---------------------------------------------------------------------
# Draft
# ---------------------------------------------------------------------

class Draft(Base):
    __tablename__ = "drafts"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)

    kind = Column(String(32), default="email")  # email | note

    content = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="drafts")


# ---------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)

    request_text = Column(Text, nullable=False)

    # Stored as JSON strings (SQLite MVP choice)
    proposed_actions_json = Column(Text, nullable=False)

    approved_actions_json = Column(Text, nullable=False)

    result_json = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audits")