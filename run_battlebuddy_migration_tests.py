from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def main() -> int:
    tests = [
        ("old titan_core imports still work", test_old_imports_work),
        ("new titan_battlebuddy imports work", test_new_imports_work),
        ("FastAPI app boots", test_app_boots),
        ("UI loads", test_ui_loads),
        ("Titan-AI integration still works", test_titan_ai_integration),
        ("chat endpoint still functions", test_chat_endpoint_still_functions),
    ]

    print("Titan BattleBuddy Migration Tests")
    print()

    failures = 0
    for label, test_fn in tests:
        try:
            test_fn()
            print(f"[PASS] {label}")
        except AssertionError as error:
            failures += 1
            print(f"[FAIL] {label}: {str(error).strip() or 'assertion failed'}")

    print()
    if failures:
        print(f"Migration tests finished with {failures} failure(s).")
        return 1

    print("All BattleBuddy migration tests passed.")
    return 0


def test_old_imports_work() -> None:
    from titan_core.main import app as old_app

    assert old_app.title == "Titan BattleBuddy"


def test_new_imports_work() -> None:
    from titan_battlebuddy.main import app as new_app
    from titan_battlebuddy.api.chat import router as chat_router

    assert new_app.title == "Titan BattleBuddy"
    assert chat_router is not None


def test_app_boots() -> None:
    from titan_battlebuddy.main import app

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "titan-battlebuddy"
    assert payload["ai_engine"] == "Titan-AI"


def test_ui_loads() -> None:
    from titan_battlebuddy.main import app

    client = TestClient(app)
    response = client.get("/ui/index.html")
    assert response.status_code == 200
    assert "Titan BattleBuddy" in response.text


def test_titan_ai_integration() -> None:
    from titan_core.brain import run_brain
    from titan_core.schemas import BrainInput, ChatMessage

    with patch("titan_core.brain.generate_assistant_response") as generate_mock:
        generate_mock.return_value = type("Result", (), {"reply": "bridge ok", "proposed_actions": []})()
        output = run_brain(
            BrainInput(
                user_id=1,
                role="owner",
                mode="personal_general",
                tools=[],
                messages=[ChatMessage(role="user", content="hello")],
            )
        )
        assert output.reply == "bridge ok"


def test_chat_endpoint_still_functions() -> None:
    from titan_battlebuddy.main import app

    client = TestClient(app)

    with (
        patch("titan_core.api.chat.get_default_mvp_user") as user_mock,
        patch("titan_core.api.chat.plan_agent_or_plan", return_value=None),
        patch("titan_core.api.chat.run_brain") as run_brain_mock,
    ):
        user_mock.return_value = type("User", (), {"id": 1, "role": "owner", "username": "owner"})()
        run_brain_mock.return_value = type("BrainOutput", (), {"reply": "BattleBuddy reply ok", "proposed_actions": []})()
        response = client.post(
            "/api/chat",
            json={"message": "Why is my route 404?", "mode": "development_assistant", "web_enabled": False},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply"].startswith("BattleBuddy reply ok")
    assert payload["route_used"] == "development_assistant"
