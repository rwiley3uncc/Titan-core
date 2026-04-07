"""
Titan Core - Main API Entrypoint
--------------------------------

Purpose:
    Initializes and starts the FastAPI backend for Titan.

Architecture Role:
    - Bootstraps FastAPI application
    - Mounts the Titan UI
    - Registers API routers
    - Provides health + root endpoints
    - Creates database tables
    - Seeds a default development user
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from titan_core.api.chat import router as chat_router
from titan_core.api.execute import router as execute_router
from titan_core.api.sitrep import router as sitrep_router
from titan_core.db import Base, SessionLocal, engine
from titan_core.models import User
import titan_core.models


app = FastAPI(
    title="Titan Core",
    version="0.2.0",
    description="Titan Personal AI Assistant",
)

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR.parent / "titan_ui"

if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")
else:
    print(f"[WARNING] titan_ui folder not found at: {UI_DIR}")

app.include_router(chat_router, prefix="/api")
app.include_router(execute_router, prefix="/api")
app.include_router(sitrep_router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return """
    <h1>Titan Personal Assistant</h1>
    <p>Titan backend is running.</p>
    <ul>
      <li><a href="/ui/index.html">Open Titan Interface</a></li>
      <li><a href="/health">Health Check</a></li>
      <li><a href="/api/chat">Chat API</a></li>
      <li><a href="/api/sitrep">Sitrep API</a></li>
    </ul>
    """


@app.get("/health", response_class=JSONResponse)
def health_check() -> dict:
    return {
        "status": "ok",
        "service": "titan-core",
        "mode": "personal-assistant",
        "features": ["chat", "memory", "sitrep", "planning"],
    }


@app.post("/seed", response_class=JSONResponse)
def seed_default_user() -> dict:
    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == "ron").first()
        if existing:
            return {
                "status": "ok",
                "message": "Default user already exists.",
                "username": existing.username,
                "role": existing.role,
            }

        user = User(
            username="ron",
            password_hash="dev-only-password",
            role="owner",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        return {
            "status": "ok",
            "message": "Default user created.",
            "username": user.username,
            "role": user.role,
        }
    finally:
        db.close()
