"""Deployment readiness must describe real, recent forecasts, with no network or ML dependencies."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from api.snapshot import manifest


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "outlook").mkdir()
        (self.root / "places.json").write_text(json.dumps([{"id": "test"}]))
        self.now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def snapshot(self, run=None, date="2026-10-24", value=.2):
        (self.root / "outlook/test.json").write_text(json.dumps({"tiles": [{
            "tile": "water", "run_ts": run, "days": [{"date": date, "value": value}]
        }]}))
        return manifest(self.root, self.now)

    def test_missing_forecast_is_unavailable(self):
        self.assertEqual(self.snapshot()["forecast_status"], "unavailable")

    def test_recent_today_forecast_is_ready(self):
        result = self.snapshot(self.now.isoformat())
        self.assertEqual(result["forecast_status"], "ready")
        self.assertEqual(result["forecast_places"]["water"], 1)

    def test_old_issue_cannot_be_marked_ready(self):
        self.assertEqual(self.snapshot((self.now - timedelta(hours=7)).isoformat())["forecast_status"], "unavailable")

    def test_yesterday_and_missing_values_cannot_be_marked_ready(self):
        self.assertEqual(self.snapshot(self.now.isoformat(), date="2026-10-23")["forecast_status"], "unavailable")
        self.assertEqual(self.snapshot(self.now.isoformat(), value=None)["forecast_status"], "unavailable")

    def test_future_and_invalid_issue_times_are_unavailable(self):
        self.assertEqual(self.snapshot((self.now + timedelta(hours=2)).isoformat())["forecast_status"], "unavailable")
        self.assertEqual(self.snapshot("invalid")["forecast_status"], "unavailable")

    def test_metadata_never_contains_keys(self):
        with patch.dict("os.environ", {"NEXT_PUBLIC_SUPABASE_URL": "https://example.invalid", "NEXT_PUBLIC_SUPABASE_ANON_KEY": "not-a-real-key"}):
            result = self.snapshot(self.now.isoformat())
        self.assertTrue(result["reporting_configured"])
        self.assertNotIn("not-a-real-key", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
