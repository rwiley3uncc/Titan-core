from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from titan_core.api import chat as chat_api
from titan_core.schemas import BrainOutput, ChatRequest


FAKE_USER = SimpleNamespace(id=1, role="owner", username="owner")


class ChatRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = object()
        self.log_patch = patch.object(chat_api, "log_action", autospec=True)
        self.entry_patch = patch.object(
            chat_api,
            "make_action_log_entry",
            autospec=True,
            return_value=SimpleNamespace(timestamp=0.0),
        )
        self.log_patch.start()
        self.entry_patch.start()
        self.addCleanup(self.log_patch.stop)
        self.addCleanup(self.entry_patch.stop)

    def test_personal_assistant_preserves_sitrep_answers(self) -> None:
        payload = {
            "generated_at": "2026-05-05T09:00:00",
            "today": [
                {
                    "title": "Calculus homework",
                    "due_at": "2026-05-05T17:00:00",
                    "course_name": "Calculus I",
                    "source": "Canvas",
                }
            ],
            "must_do_today": [],
            "still_open": [],
            "suggested_blocks": [],
            "source_counts": {"canvas": 1},
            "configuration": {
                "canvas_feed_configured": True,
                "outlook_feed_configured": False,
            },
        }
        with (
            patch.object(chat_api, "get_default_mvp_user", return_value=FAKE_USER),
            patch.object(chat_api, "plan_agent_or_plan", return_value=None),
            patch.object(chat_api, "build_sitrep_payload", return_value=payload),
            patch.object(chat_api, "find_memory_match", return_value=None),
        ):
            response = chat_api.chat(
                ChatRequest(message="What do I need to do today?", mode="personal_general"),
                db=self.db,
            )

        self.assertEqual(response.route_used, "personal_grounded")
        self.assertEqual(response.source_status, "verified")
        self.assertIn("sitrep payload", response.source_names)
        self.assertIn("Based on the current sitrep/dashboard data", response.reply)

    def test_personal_assistant_refuses_unverified_general_knowledge(self) -> None:
        with (
            patch.object(chat_api, "get_default_mvp_user", return_value=FAKE_USER),
            patch.object(chat_api, "plan_agent_or_plan", return_value=None),
            patch.object(chat_api, "find_memory_match", return_value=None),
        ):
            response = chat_api.chat(
                ChatRequest(message="Explain Newton's method in Calculus.", mode="personal_general"),
                db=self.db,
            )

        self.assertEqual(response.route_used, "verified_knowledge")
        self.assertEqual(response.source_status, "missing_verified_source")
        self.assertEqual(response.source_names, [])
        self.assertEqual(
            response.reply,
            "I don't have enough verified information to answer that yet. "
            "Add a course document, approved source, or verified reference, and I can help from that.",
        )

    def test_personal_assistant_uses_uploaded_verified_source(self) -> None:
        def fake_run_brain(inp, db=None, user_id=None):
            source_message = "\n".join(message.content for message in inp.messages)
            self.assertIn("calculus_notes.md", source_message)
            self.assertIn("Newton's method finds roots", source_message)
            return BrainOutput(
                reply="Based on `calculus_notes.md`, Newton's method is an iterative root-finding method.",
                proposed_actions=[],
            )

        with (
            patch.object(chat_api, "get_default_mvp_user", return_value=FAKE_USER),
            patch.object(chat_api, "plan_agent_or_plan", return_value=None),
            patch.object(chat_api, "run_brain", side_effect=fake_run_brain),
            patch.object(chat_api, "find_memory_match", return_value=None),
        ):
            response = chat_api.chat(
                ChatRequest(
                    message="Explain Newton's method from this.",
                    mode="personal_general",
                    file_name="calculus_notes.md",
                    file_content="Newton's method finds roots by repeatedly refining an estimate.",
                ),
                db=self.db,
            )

        self.assertEqual(response.route_used, "verified_knowledge")
        self.assertEqual(response.source_status, "verified")
        self.assertEqual(response.source_names, ["calculus_notes.md"])
        self.assertIn("Based on `calculus_notes.md`", response.reply)

    def test_development_assistant_still_provides_general_guidance(self) -> None:
        with (
            patch.object(chat_api, "get_default_mvp_user", return_value=FAKE_USER),
            patch.object(chat_api, "plan_agent_or_plan", return_value=None),
            patch.object(
                chat_api,
                "run_brain",
                return_value=BrainOutput(
                    reply="Check whether your router is mounted with the expected prefix and method.",
                    proposed_actions=[],
                ),
            ),
        ):
            response = chat_api.chat(
                ChatRequest(
                    message="Why is my FastAPI route returning 404?",
                    mode="development_assistant",
                ),
                db=self.db,
            )

        self.assertEqual(response.route_used, "development_assistant")
        self.assertEqual(response.source_status, "unverified_general_guidance")
        self.assertTrue(response.reply.startswith("Check whether your router"))

    def test_main_imports_successfully(self) -> None:
        from titan_core.main import app

        self.assertIsNotNone(app)


if __name__ == "__main__":
    unittest.main()
