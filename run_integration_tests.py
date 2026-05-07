from __future__ import annotations

from titan_core.brain import run_brain
from titan_core.schemas import BrainInput, BrainOutput, ChatMessage


def main() -> int:
    tests = [
        ("Titan-core can call Titan-AI", test_core_calls_titan_ai),
        ("reply flow still works", test_reply_flow),
        ("fallback handling still works", test_fallback_handling),
    ]

    print("Titan Core / Titan-AI Integration Tests")
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
        print(f"Integration tests finished with {failures} failure(s).")
        return 1

    print("All integration tests passed.")
    return 0


def _request(message: str, mode: str = "personal_general") -> BrainInput:
    return BrainInput(
        user_id=1,
        role="owner",
        mode=mode,
        tools=[],
        messages=[ChatMessage(role="user", content=message)],
    )


def test_core_calls_titan_ai() -> None:
    import titan_core.brain as core_brain

    original = core_brain.generate_assistant_response

    def _fake_generate(*args, **kwargs):
        return BrainOutput(reply="bridge ok", proposed_actions=[])

    try:
        core_brain.generate_assistant_response = _fake_generate
        output = run_brain(_request("hello"))
        assert output.reply == "bridge ok"
    finally:
        core_brain.generate_assistant_response = original


def test_reply_flow() -> None:
    import titan_ai.brain_router as brain_router

    original = brain_router.generate_local_reply

    def _fake_reply(prompt: str, system_prompt: str = "") -> str | None:
        return "reply path ok"

    try:
        brain_router.generate_local_reply = _fake_reply
        output = run_brain(_request("hello there"))
        assert output.reply == "reply path ok"
    finally:
        brain_router.generate_local_reply = original


def test_fallback_handling() -> None:
    import titan_ai.brain_router as brain_router

    original = brain_router.generate_local_reply

    def _no_reply(prompt: str, system_prompt: str = "") -> str | None:
        return None

    try:
        brain_router.generate_local_reply = _no_reply
        output = run_brain(_request("what time is it"))
        assert output.reply.startswith("It is ")
    finally:
        brain_router.generate_local_reply = original


if __name__ == "__main__":
    raise SystemExit(main())
