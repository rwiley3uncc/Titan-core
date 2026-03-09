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

Run (from project root):
    uvicorn titan_core.main:app --reload

Access:
    Backend root: http://127.0.0.1:8000
    UI:           http://127.0.0.1:8000/ui/index.html

Author:
    Ron Wiley
Project:
    Titan AI - Personal Assistant Core
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Controller routers
from titan_core.api.chat import router as chat_router


# ---------------------------------------------------------------------
# Application Initialization
# ---------------------------------------------------------------------

app = FastAPI(
    title="Titan Core",
    version="0.1.0",
    description="Titan Personal AI Assistant",
)


# ---------------------------------------------------------------------
# Directory Configuration
# ---------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

# UI folder lives one level up from titan_core
UI_DIR = BASE_DIR.parent / "titan_ui"


# ---------------------------------------------------------------------
# Static UI Mount
# ---------------------------------------------------------------------

if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")
else:
    print(f"[WARNING] titan_ui folder not found at: {UI_DIR}")


# ---------------------------------------------------------------------
# API Routers
# ---------------------------------------------------------------------

app.include_router(chat_router, prefix="/api")


# ---------------------------------------------------------------------
# Root Endpoint
# ---------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return """
    <h1>Titan Personal Assistant</h1>
    <p>Titan backend is running.</p>
    <ul>
      <li><a href="/ui/index.html">Open Titan Interface</a></li>
      <li><a href="/health">Health Check</a></li>
      <li><a href="/api/chat">API Endpoint</a></li>
    </ul>
    """


# ---------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------

@app.get("/health", response_class=JSONResponse)
def health_check() -> dict:
    return {
        "status": "ok",
        "service": "titan-core",
        "mode": "personal-assistant"
    }