from __future__ import annotations

import json
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from titan_core import calendar_store
from titan_core.main import app
from titan_core.api import sitrep as sitrep_api


class CalendarStoreReadPathTests(unittest.TestCase):
    def _patch_store_paths(self, root: Path):
        data_dir = root / "data"
        store_path = data_dir / "calendar_sources.json"
        return patch.multiple(
            calendar_store,
            DATA_DIR=data_dir,
            CALENDAR_SOURCES_PATH=store_path,
        )

    def test_missing_calendar_source_file_uses_in_memory_defaults_without_creating_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self._patch_store_paths(root):
                records, warnings = calendar_store.list_calendar_sources_with_diagnostics()

            self.assertEqual({record.id for record in records}, {"school_canvas", "personal_outlook"})
            self.assertTrue(any("missing" in warning.lower() for warning in warnings))
            self.assertFalse((root / "data" / "calendar_sources.json").exists())

    def test_malformed_calendar_source_file_uses_defaults_without_rewriting_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            store_path = data_dir / "calendar_sources.json"
            original_text = "{bad json}\n"
            store_path.write_text(original_text, encoding="utf-8")

            with self._patch_store_paths(root):
                records, warnings = calendar_store.list_calendar_sources_with_diagnostics()

            self.assertEqual({record.id for record in records}, {"school_canvas", "personal_outlook"})
            self.assertTrue(any("malformed" in warning.lower() for warning in warnings))
            self.assertEqual(store_path.read_text(encoding="utf-8"), original_text)

    def test_read_only_calendar_source_file_does_not_require_write_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            store_path = data_dir / "calendar_sources.json"
            payload = [
                {
                    "id": "custom_canvas",
                    "name": "Custom Canvas",
                    "type": "canvas",
                    "url": "https://example.com/feed.ics",
                    "enabled": True,
                    "created_at": "2026-05-13T00:00:00",
                    "updated_at": "2026-05-13T00:00:00",
                }
            ]
            original_text = json.dumps(payload, indent=2) + "\n"
            store_path.write_text(original_text, encoding="utf-8")
            store_path.chmod(stat.S_IREAD)

            try:
                with self._patch_store_paths(root):
                    records, warnings = calendar_store.list_calendar_sources_with_diagnostics()
            finally:
                store_path.chmod(stat.S_IWRITE | stat.S_IREAD)

            self.assertEqual(records[0].id, "custom_canvas")
            self.assertEqual(warnings, [])
            self.assertEqual(store_path.read_text(encoding="utf-8"), original_text)


class SitrepGracefulDegradationTests(unittest.TestCase):
    def test_api_sitrep_degrades_when_calendar_source_storage_is_unavailable(self) -> None:
        client = TestClient(app)
        fake_settings = SimpleNamespace(
            configured_calendar_sources=lambda: [],
            canvas_ics_url="",
            outlook_ics_url="",
            outlook_calendar_email="",
            calendar_sources_json="",
            sitrep_time=sitrep_api.settings.sitrep_time,
            study_block_minutes=sitrep_api.settings.study_block_minutes,
        )

        with (
            patch("titan_core.api.sitrep.list_calendar_sources_with_diagnostics", return_value=([], ["Local calendar source storage is unavailable; using in-memory defaults."])),
            patch("titan_core.api.sitrep.tasks_as_planner_items", return_value=[]),
            patch("titan_core.api.sitrep.fetch_weather_summary", return_value="Clear skies."),
            patch.object(sitrep_api, "settings", fake_settings),
        ):
            response = client.get("/api/sitrep")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("warnings", payload)
        self.assertTrue(any("unavailable" in warning.lower() for warning in payload["warnings"]))


if __name__ == "__main__":
    unittest.main()
