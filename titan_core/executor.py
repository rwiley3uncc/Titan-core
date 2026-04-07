import subprocess
import webbrowser


def execute_action(action):

    action_type = action.get("type") or action.get("action")

    if action_type == "open_app":

        app = action.get("app")

        if app == "edge":
            subprocess.Popen(
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            )
            return {"status": "executed"}

        elif app == "vscode":
            subprocess.Popen(
                r"C:\Users\mouse\AppData\Local\Programs\Microsoft VS Code\Code.exe"
            )
            return {"status": "executed"}

        else:
            return {"status": "unknown_app"}

    elif action_type == "open_url":

        url = action.get("url")
        webbrowser.open(url)

        return {"status": "executed"}

    return {"status": "unknown_action"}