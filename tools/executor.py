"""
executor.py

Purpose:
Execute actions proposed by Titan's rules or AI system.

Example action:
{
    "type": "open_app",
    "app": "vscode"
}
"""

import subprocess
import os
import webbrowser

# -------------------------------------------------------------------
# App Launch Map
# -------------------------------------------------------------------
# Map Titan app names → actual system commands
APP_COMMANDS = {

    "vscode": [
        r"C:\Users\%USERNAME%\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        "code"
    ],

    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    ],

    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    ],

    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe"
    ],

    "powershell": [
        "powershell"
    ],

    "cmd": [
        "cmd"
    ],

    "explorer": [
        "explorer"
    ],

    "notepad": [
        "notepad"
    ],

    "calculator": [
        "calc"
    ]
}

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def expand_path(path):
    """Expand environment variables like %USERNAME%"""
    return os.path.expandvars(path)


def try_launch(commands):
    """
    Try each command until one works.
    """
    for cmd in commands:
        try:
            cmd = expand_path(cmd)
            subprocess.Popen(cmd)
            return True
        except Exception:
            continue
    return False


# -------------------------------------------------------------------
# Action Executors
# -------------------------------------------------------------------

def open_app(app_name):
    """
    Launch an application by name.
    """
    commands = APP_COMMANDS.get(app_name)

    if not commands:
        return {
            "status": "error",
            "message": f"Unknown app: {app_name}"
        }

    success = try_launch(commands)

    if success:
        return {
            "status": "ok",
            "message": f"Opened {app_name}"
        }

    return {
        "status": "error",
        "message": f"Failed to launch {app_name}"
    }


# -------------------------------------------------------------------
# Main Action Router
# -------------------------------------------------------------------

def execute_action(action):
    """
    Main entry point.
    """
    action_type = action.get("type")

    if action_type == "open_app":
        return open_app(action.get("app"))

    return {
        "status": "ignored",
        "message": f"No executor for action type: {action_type}"
    }


# -------------------------------------------------------------------
# Manual Test
# -------------------------------------------------------------------

if __name__ == "__main__":

    test_action = {
        "type": "open_app",
        "app": "vscode"
    }

    result = execute_action(test_action)
    print(result)