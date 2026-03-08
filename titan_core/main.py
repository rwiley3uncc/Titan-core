"""
Titan Core - Main API Entrypoint
---------------------------------

Purpose:
    Initializes and starts the FastAPI backend for Titan Core.

Role in Architecture:
    - Bootstraps FastAPI application
    - Mounts static UI
    - Registers API routers (controller layer lives in /titan_core/api)
    - Provides health and root endpoints

How to Run (from project root):
    uvicorn main:app --reload

Access:
    Backend root: http://127.0.0.1:8000
    UI:           http://127.0.0.1:8000/ui/index.html

Author:
    Ron Wiley
Project:
    Titan AI - Operational Personnel Assistant
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Import routers (controller layer)
# NOTE: These imports assume your python package is titan_core/
from titan_core.api.chat import router as chat_router


# ---------------------------------------------------------------------
# Application Initialization
# ---------------------------------------------------------------------

app = FastAPI(
    title="Titan Core",
    version="0.1.0",
    description="Operational Personnel Assistant AI - MVP",
)


# ---------------------------------------------------------------------
# Directory Configuration
# ---------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR / "titan_ui"


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

# All API endpoints under /api/*
app.include_router(chat_router, prefix="/api")


# ---------------------------------------------------------------------
# Root Endpoint
# ---------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def root() -> str:
    """
    Basic landing page to confirm backend is operational.
    """
    return """
    <h1>Titan Core</h1>
    <p>Backend is running.</p>
    <ul>
      <li><a href="/ui/index.html">Open UI</a></li>
      <li><a href="/health">Health Check</a></li>
      <li><a href="/api/chat">API: Chat (GET info)</a></li>
    </ul>
    """


# ---------------------------------------------------------------------
# Health Check Endpoint
# ---------------------------------------------------------------------

@app.get("/health", response_class=JSONResponse)
def health_check() -> dict:
    """
    Simple health endpoint for monitoring / deployment checks.
    """
    return {"status": "ok", "service": "titan-core"}