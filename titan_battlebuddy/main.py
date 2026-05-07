"""Titan BattleBuddy - Main API Entrypoint.

BattleBuddy is the user-facing operational assistant/controller layer for the
Titan platform. Titan-AI now owns the AI engine path.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from titan_core.api.calendar_sources import router as calendar_sources_router
from titan_core.api.chat import router as chat_router
from titan_core.api.execute import router as execute_router
from titan_core.api.sitrep import router as sitrep_router
from titan_core.config import get_search_provider, is_verified_web_enabled, settings
from titan_core.db import Base, SessionLocal, engine
from titan_core.models import User
from titan_core.titan_shared_imports import ensure_titan_shared_on_path
import titan_core.models

ensure_titan_shared_on_path()

from titan_shared.logging_utils import configure_local_logging  # noqa: E402

configure_local_logging("INFO")


app = FastAPI(
    title="Titan BattleBuddy",
    version="0.3.0",
    description="Titan BattleBuddy operational assistant for school, life, and safe local workflows",
)

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR.parent / "titan_ui"

if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")
else:
    print(f"[WARNING] titan_ui folder not found at: {UI_DIR}")

app.include_router(chat_router, prefix="/api")
app.include_router(calendar_sources_router, prefix="/api")
app.include_router(execute_router, prefix="/api")
app.include_router(sitrep_router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return """
    <h1>Titan BattleBuddy</h1>
    <p>Titan BattleBuddy backend is running.</p>
    <ul>
      <li><a href="/ui/index.html">Open Titan BattleBuddy Interface</a></li>
      <li><a href="/health">Health Check</a></li>
      <li><a href="/api/chat">Chat API</a></li>
      <li><a href="/api/memory">Memory API</a></li>
      <li><a href="/api/sitrep">Sitrep API</a></li>
    </ul>
    """


@app.get("/health", response_class=JSONResponse)
def health_check() -> dict:
    return {
        "status": "ok",
        "service": "titan-battlebuddy",
        "mode": "battlebuddy-controller",
        "owner_username": settings.owner_username,
        "features": ["chat", "memory", "planning", "sitrep"],
        "compatibility_namespace": "titan_core",
        "ai_engine": "Titan-AI",
    }


@app.post("/seed", response_class=JSONResponse)
def seed_default_user() -> dict:
    db: Session = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == settings.owner_username).first()
        if existing:
            return {
                "status": "ok",
                "message": "Default user already exists.",
                "username": existing.username,
                "role": existing.role,
            }

        user = User(username=settings.owner_username, password_hash="dev-only-password", role="owner")
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


@app.get("/debug/verified-web", response_class=JSONResponse)
def debug_verified_web() -> dict:
    return {
        "env_enabled": is_verified_web_enabled(),
        "provider": get_search_provider(),
    }
