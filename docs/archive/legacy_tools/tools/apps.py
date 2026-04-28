from __future__ import annotations

import os
import subprocess
from pathlib import Path


APP_MAP = {
    "vscode": r"C:\Users\mouse\AppData\Local\Programs\Microsoft VS Code\Code.exe",
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "powershell": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
}


FOLDER_MAP = {
    "titan": r"C:\Users\mouse\dev\titancore",
    "downloads": str(Path.home() / "Downloads"),
    "desktop": str(Path.home() / "Desktop"),
}


def open_app(name: str) -> dict:
    key = (name or "").strip().lower()

    if key not in APP_MAP:
        return {"ok": False, "error": f"Unknown app: {name}"}

    path = APP_MAP[key]

    if not os.path.exists(path):
        return {"ok": False, "error": f"App path not found: {path}"}

    subprocess.Popen([path])
    return {"ok": True, "type": "open_app", "app": key}


def open_folder(name: str) -> dict:
    key = (name or "").strip().lower()

    if key not in FOLDER_MAP:
        return {"ok": False, "error": f"Unknown folder: {name}"}

    path = FOLDER_MAP[key]

    if not os.path.exists(path):
        return {"ok": False, "error": f"Folder path not found: {path}"}

    os.startfile(path)
    return {"ok": True, "type": "open_folder", "folder": key, "path": path}