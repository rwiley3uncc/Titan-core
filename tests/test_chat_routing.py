from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from titan_core.api import chat as chat_api
from titan_core.schemas import BrainOutput, ChatRequest
from titan_core import verified_web
from titan_core.verified_web import VerifiedWebResult, VerifiedWebSource, build_verified_web_context, filter_trusted_results, is_allowed_searxng_url, is_trusted_url


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
        self.assertEqual(response.source_type, "sitrep")
        self.assertEqual(response.source_status, "grounded")
        self.assertEqual(response.source_label, "Source: Sitrep / Dashboard")
        self.assertIn("sitrep payload", response.source_names)
        self.assertIn("Based on the current sitrep/dashboard data", response.reply)

    def test_personal_assistant_refuses_unverified_general_knowledge(self) -> None:
        with (
            patch.object(chat_api, "get_default_mvp_user", return_value=FAKE_USER),
            patch.object(chat_api, "plan_agent_or_plan", return_value=None),
            patch.object(chat_api, "find_memory_match", return_value=None),
            patch.object(chat_api.settings, "verified_web_enabled", False),
        ):
            response = chat_api.chat(
                ChatRequest(message="Explain Newton's method in Calculus.", mode="personal_general", web_enabled=False),
                db=self.db,
            )

        self.assertEqual(response.route_used, "verified_knowledge")
        self.assertEqual(response.source_status, "missing_verified_source")
        self.assertEqual(response.source_names, [])
        self.assertEqual(
            response.reply,
            "I don't have a verified source for that topic yet.\n\n"
            "You can:\n"
            "- upload your course notes or textbook\n"
            "- add an approved source\n"
            "- enable verified web lookup\n\n"
            "Then I can help using trusted information.",
        )

    def test_current_fact_refuses_when_verified_web_disabled(self) -> None:
        with (
            patch.object(chat_api, "get_default_mvp_user", return_value=FAKE_USER),
            patch.object(chat_api, "plan_agent_or_plan", return_value=None),
            patch.object(chat_api, "find_memory_match", return_value=None),
            patch.object(chat_api.settings, "verified_web_enabled", False),
        ):
            response = chat_api.chat(
                ChatRequest(message="Who is the current CEO of OpenAI?", mode="personal_general", web_enabled=False),
                db=self.db,
            )

        self.assertEqual(response.route_used, "verified_knowledge")
        self.assertEqual(response.reply, "I don't have a verified current source for that yet.\n\nYou can:\n- enable verified web lookup\n- add an approved web source\n- upload a trusted reference\n\nThen I can answer from verified information.")

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
                    web_enabled=False,
                    file_name="calculus_notes.md",
                    file_content="Newton's method finds roots by repeatedly refining an estimate.",
                ),
                db=self.db,
            )

        self.assertEqual(response.route_used, "verified_knowledge")
        self.assertEqual(response.source_type, "uploaded_file")
        self.assertEqual(response.source_status, "verified_source")
        self.assertEqual(response.source_label, "Source: Uploaded Verified File")
        self.assertEqual(response.source_names, ["calculus_notes.md"])
        self.assertIn("Based on `calculus_notes.md`", response.reply)

    def test_trusted_url_filter_accepts_approved_domains(self) -> None:
        self.assertTrue(is_trusted_url("https://khanacademy.org/math"))
        self.assertTrue(is_trusted_url("https://www.khanacademy.org/math"))
        self.assertTrue(is_trusted_url("https://docs.python.org/3/tutorial/"))
        self.assertTrue(is_trusted_url("https://subdomain.mit.edu/course"))

    def test_trusted_url_filter_rejects_random_domains(self) -> None:
        self.assertFalse(is_trusted_url("https://random-blog-example.com/post"))
        self.assertFalse(is_trusted_url("https://khanacademy.org.fake-site.com/topic"))
        self.assertFalse(is_trusted_url("https://openai.fake-example.com"))

    def test_filter_trusted_results_keeps_only_approved_urls(self) -> None:
        filtered = filter_trusted_results(
            [
                {"title": "Python Docs", "url": "https://docs.python.org/3/"},
                {"title": "Random", "url": "https://random-blog-example.com/post"},
            ]
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["title"], "Python Docs")

    def test_verified_web_disabled_makes_no_network_call(self) -> None:
        sentinel = Mock(side_effect=AssertionError("network should not be called"))
        with patch.object(verified_web.settings, "verified_web_enabled", False):
            result = build_verified_web_context("python latest", search_fn=sentinel)
        self.assertIsNone(result)
        sentinel.assert_not_called()

    def test_web_toggle_off_prevents_provider_call_even_if_env_true(self) -> None:
        with (
            patch.object(chat_api, "get_default_mvp_user", return_value=FAKE_USER),
            patch.object(chat_api, "plan_agent_or_plan", return_value=None),
            patch.object(chat_api, "find_memory_match", return_value=None),
            patch.object(chat_api.settings, "verified_web_enabled", True),
            patch.object(chat_api, "build_verified_web_context", side_effect=AssertionError("provider should not be called")),
        ):
            response = chat_api.chat(
                ChatRequest(message="What is the latest version of Python?", mode="personal_general", web_enabled=False),
                db=self.db,
            )
        self.assertEqual(response.route_used, "verified_knowledge")

    def test_env_off_prevents_provider_call_even_if_toggle_on(self) -> None:
        with (
            patch.object(chat_api, "get_default_mvp_user", return_value=FAKE_USER),
            patch.object(chat_api, "plan_agent_or_plan", return_value=None),
            patch.object(chat_api, "find_memory_match", return_value=None),
            patch.object(chat_api.settings, "verified_web_enabled", False),
            patch.object(chat_api, "build_verified_web_context", side_effect=AssertionError("provider should not be called")),
        ):
            response = chat_api.chat(
                ChatRequest(message="What is the latest version of Python?", mode="personal_general", web_enabled=True),
                db=self.db,
            )
        self.assertEqual(response.route_used, "verified_knowledge")

    def test_both_true_allows_provider_call(self) -> None:
        trusted_web = VerifiedWebResult(
            query="latest version of Python",
            source_status="snippet_only",
            confidence="medium",
            sources=[
                VerifiedWebSource(
                    title="Python.org",
                    url="https://www.python.org/downloads/",
                    domain="python.org",
                    extracted_text="Python 3.14.0 is the latest release.",
                    source_status="snippet_only",
                )
            ],
        )
        with (
            patch.object(chat_api, "get_default_mvp_user", return_value=FAKE_USER),
            patch.object(chat_api, "plan_agent_or_plan", return_value=None),
            patch.object(chat_api, "find_memory_match", return_value=None),
            patch.object(chat_api.settings, "verified_web_enabled", True),
            patch.object(chat_api, "build_verified_web_context", return_value=trusted_web) as provider_mock,
            patch.object(chat_api, "run_brain", return_value=BrainOutput(reply="Python 3.14.0 is the latest release.", proposed_actions=[])),
        ):
            response = chat_api.chat(
                ChatRequest(message="What is the latest version of Python?", mode="personal_general", web_enabled=True),
                db=self.db,
            )
        provider_mock.assert_called_once()
        self.assertEqual(response.source_type, "verified_web")

    def test_missing_provider_or_key_fails_closed(self) -> None:
        with (
            patch.object(verified_web.settings, "verified_web_enabled", True),
            patch.object(verified_web.settings, "search_provider", "brave"),
            patch.object(verified_web.settings, "search_api_key", None),
            patch("titan_core.verified_web.urlopen", side_effect=AssertionError("network should not be called")),
        ):
            result = build_verified_web_context("python latest")
        self.assertIsNone(result)

    def test_searxng_url_validation_works(self) -> None:
        self.assertTrue(is_allowed_searxng_url("http://127.0.0.1:8080"))
        self.assertTrue(is_allowed_searxng_url("http://localhost:8080"))
        self.assertTrue(is_allowed_searxng_url("http://192.168.1.10:8080"))
        self.assertFalse(is_allowed_searxng_url("https://search.example.com"))

    def test_mocked_searxng_trusted_results_succeed(self) -> None:
        payload = {
            "results": [
                {"title": "Python.org", "url": "https://www.python.org/downloads/", "content": "Latest Python release."},
                {"title": "Blog", "url": "https://random-blog-example.com/post", "content": "Random."},
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self):
                import json as _json
                return _json.dumps(payload).encode("utf-8")

        with (
            patch.object(verified_web.settings, "verified_web_enabled", True),
            patch.object(verified_web.settings, "search_provider", "searxng"),
            patch.object(verified_web.settings, "searxng_url", "http://127.0.0.1:8080"),
            patch("titan_core.verified_web.urlopen", return_value=FakeResponse()),
        ):
            result = build_verified_web_context("python latest")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual([source.title for source in result.sources], ["Python.org"])

    def test_mocked_searxng_untrusted_results_fail_closed(self) -> None:
        payload = {
            "results": [
                {"title": "Blog", "url": "https://random-blog-example.com/post", "content": "Random."},
            ]
        }

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self):
                import json as _json
                return _json.dumps(payload).encode("utf-8")

        with (
            patch.object(verified_web.settings, "verified_web_enabled", True),
            patch.object(verified_web.settings, "search_provider", "searxng"),
            patch.object(verified_web.settings, "searxng_url", "http://127.0.0.1:8080"),
            patch("titan_core.verified_web.urlopen", return_value=FakeResponse()),
        ):
            result = build_verified_web_context("python latest")
        self.assertIsNone(result)

    def test_mocked_brave_provider_results_are_filtered(self) -> None:
        with patch.object(verified_web.settings, "verified_web_enabled", True):
            result = build_verified_web_context(
                "python latest",
                search_fn=lambda query: [
                    {"title": "Python.org", "url": "https://www.python.org/downloads/", "snippet": "Latest Python release."},
                    {"title": "Blog", "url": "https://random-blog-example.com/post", "snippet": "Random post."},
                ],
            )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual([source.title for source in result.sources], ["Python.org"])
        self.assertEqual(result.source_status, "snippet_only")

    def test_mocked_provider_with_only_untrusted_results_returns_none(self) -> None:
        with patch.object(verified_web.settings, "verified_web_enabled", True):
            result = build_verified_web_context(
                "python latest",
                search_fn=lambda query: [
                    {"title": "Blog", "url": "https://random-blog-example.com/post", "snippet": "Random post."},
                ],
            )
        self.assertIsNone(result)

    def test_personal_assistant_uses_mocked_verified_web_context_when_enabled(self) -> None:
        verified_web = VerifiedWebResult(
            query="latest version of Python",
            source_status="snippet_only",
            confidence="medium",
            sources=[
                VerifiedWebSource(
                    title="Python.org",
                    url="https://www.python.org/downloads/",
                    domain="python.org",
                    extracted_text="Python 3.14.0 is the latest Python 3 release.",
                    source_status="snippet_only",
                ),
                VerifiedWebSource(
                    title="Docs Python",
                    url="https://docs.python.org/3/whatsnew/",
                    domain="docs.python.org",
                    extracted_text="The What's New guide tracks current Python releases.",
                    source_status="snippet_only",
                ),
            ],
        )

        def fake_run_brain(inp, db=None, user_id=None):
            source_message = "\n".join(message.content for message in inp.messages)
            self.assertIn("Verified web sources:", source_message)
            self.assertIn("python.org", source_message)
            return BrainOutput(
                reply="The latest listed Python release is Python 3.14.0.",
                proposed_actions=[],
            )

        with (
            patch.object(chat_api, "get_default_mvp_user", return_value=FAKE_USER),
            patch.object(chat_api, "plan_agent_or_plan", return_value=None),
            patch.object(chat_api, "find_memory_match", return_value=None),
            patch.object(chat_api, "run_brain", side_effect=fake_run_brain),
            patch.object(chat_api, "build_verified_web_context", return_value=verified_web),
            patch.object(chat_api.settings, "verified_web_enabled", True),
        ):
            response = chat_api.chat(
                ChatRequest(message="What is the latest version of Python?", mode="personal_general", web_enabled=True),
                db=self.db,
            )

        self.assertEqual(response.route_used, "verified_knowledge")
        self.assertEqual(response.source_type, "verified_web")
        self.assertEqual(response.source_status, "snippet_only")
        self.assertEqual(response.source_label, "Source: Verified Web (Snippet)")
        self.assertIn("Python.org", response.source_names)
        self.assertIn("https://www.python.org/downloads/", response.source_urls)
        self.assertTrue(response.reply.startswith("Based on verified sources:"))
        self.assertIn("python.org", response.reply)
        self.assertIn("snippet_only", response.reply)

    def test_action_log_path_is_gitignored(self) -> None:
        with open(".gitignore", "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("data/action_log.json", content)

    def test_frontend_source_label_is_optional(self) -> None:
        with open("titan_ui/index.html", "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("metadata && typeof metadata.source_label === 'string'", content)
        self.assertIn("appendConversationText('TITAN', data.reply || 'No reply returned.', {", content)

    def test_frontend_web_toggle_is_present(self) -> None:
        with open("titan_ui/index.html", "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("Enable Verified Web Access", content)
        self.assertIn("WEB_ENABLED_STORAGE_KEY", content)
        self.assertIn("web_enabled: currentWebEnabled()", content)

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
                    web_enabled=False,
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
