import subprocess
import webbrowser


def execute_action(action):
    """
    Execute only the small allow-listed action set supported by Titan.

    Agent-originated proposals must stay inside this approved execution path
    and should only run after explicit user approval from the UI.
    """

    action_type = action.get("type") or action.get("action")

    if action_type == "open_edge":
        subprocess.Popen(
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        )
        return {"status": "executed", "message": "Opened Microsoft Edge."}

    if action_type == "open_vscode":
        subprocess.Popen(
            r"C:\Users\mouse\AppData\Local\Programs\Microsoft VS Code\Code.exe"
        )
        return {"status": "executed", "message": "Opened VS Code."}

    if action_type == "open_app":

        app = action.get("app")

        if app == "edge":
            subprocess.Popen(
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            )
            return {"status": "executed", "message": "Opened Microsoft Edge."}

        elif app == "vscode":
            subprocess.Popen(
                r"C:\Users\mouse\AppData\Local\Programs\Microsoft VS Code\Code.exe"
            )
            return {"status": "executed", "message": "Opened VS Code."}

        else:
            return {"status": "unknown_app", "message": "That app is not in the approved action list."}

    elif action_type == "open_url":

        url = action.get("url")
        webbrowser.open(url)

        return {"status": "executed", "message": "Opened the requested URL."}

    return {"status": "unknown_action", "message": "That action is not supported by the approved execution path."}
