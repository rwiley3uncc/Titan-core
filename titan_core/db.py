"""
Titan Core - Database Configuration
------------------------------------

Purpose:
    Configures SQLAlchemy engine, session factory,
    and declarative base for Titan Core.

Role in Architecture:
    - Provides database engine
    - Provides session dependency for FastAPI
    - Defines shared Base for all ORM models

Environment Variables:
    DATABASE_URL:
        Default: sqlite:///./titan.db
        Production example:
            postgresql+psycopg2://user:pass@host/dbname

Design Notes:
    - SQLite used for MVP
    - check_same_thread disabled for FastAPI compatibility
    - Sessions are request-scoped via dependency injection

Author:
    Ron Wiley
Project:
    Titan AI - Operational Personnel Assistant
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Generator


# ---------------------------------------------------------------------
# Database URL Configuration
# ---------------------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./titan.db")


# SQLite requires special handling for multithreaded environments
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}


# ---------------------------------------------------------------------
# Engine Initialization
# ---------------------------------------------------------------------

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    future=True,  # Enables SQLAlchemy 2.0 style behavior
    echo=False    # Set to True for SQL debug logging
)


# ---------------------------------------------------------------------
# Session Factory
# ---------------------------------------------------------------------

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# ---------------------------------------------------------------------
# Declarative Base (Shared Across Models)
# ---------------------------------------------------------------------

Base = declarative_base()


# ---------------------------------------------------------------------
# FastAPI Dependency
# ---------------------------------------------------------------------

def get_db() -> Generator:
    """
    Provides a database session per request.

    Ensures:
        - Session is opened
        - Session is closed after request
        - Prevents connection leakage
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()