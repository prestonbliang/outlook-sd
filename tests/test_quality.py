import unittest
from datetime import datetime, timedelta, timezone

from api.quality import quality


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, 1, tzinfo=timezone.utc)
        self.tile = {"days": [{"date": "2026-10-23", "value": 1}], "run_ts": self.now.isoformat(), "stale_inputs": []}

    def test_current_day_is_pacific_not_utc(self):
        self.assertEqual(quality(self.tile, self.now)["state"], "current")
        self.assertEqual(quality(self.tile, self.now)["forecast_date"], "2026-10-23")

    def test_future_only_and_null_forecasts_are_unavailable(self):
        for days in [[{"date": "2026-10-24", "value": 1}], [{"date": "2026-10-23", "value": None}], []]:
            self.assertEqual(quality({**self.tile, "days": days}, self.now)["state"], "unavailable")

    def test_old_and_untrusted_issue_times_are_stale(self):
        for run in [(self.now - timedelta(hours=7)).isoformat(), "invalid", "2026-10-23", None, (self.now + timedelta(hours=1)).isoformat()]:
            self.assertEqual(quality({**self.tile, "run_ts": run}, self.now)["state"], "stale")

    def test_daily_state_forecasts_have_daily_budget(self):
        tile = {**self.tile, "model": "calheatscore", "run_ts": (self.now - timedelta(hours=18)).isoformat()}
        self.assertEqual(quality(tile, self.now)["state"], "current")

    def test_stale_inputs_and_not_applicable_are_distinct(self):
        self.assertEqual(quality({**self.tile, "stale_inputs": ["weather"]}, self.now)["state"], "stale")
        self.assertEqual(quality({"status": "not_applicable"}, self.now)["state"], "not_applicable")

    def test_sources_can_expire_before_the_forecast_issue_time(self):
        tile = {**self.tile, "source_checks": [{"reference_at": (self.now - timedelta(hours=2)).isoformat(), "max_age_hours": 1}]}
        self.assertEqual(quality(tile, self.now)["state"], "stale")
        tile["source_checks"][0]["max_age_hours"] = 3
        self.assertEqual(quality(tile, self.now)["state"], "current")

    def test_invalid_source_timestamps_or_budgets_cannot_claim_freshness(self):
        for value in [None, [], [{"reference_at": None, "max_age_hours": 3}],
                      [{"reference_at": self.now.isoformat(), "max_age_hours": -1}]]:
            with self.subTest(value=value):
                result = quality({**self.tile, "source_checks": value}, self.now)["state"]
                self.assertEqual(result, "current" if value == [] else "stale")

    def test_missing_or_nonfinite_values_are_not_forecasts(self):
        for value in [None, float("nan"), float("inf"), True]:
            self.assertEqual(quality({**self.tile, "days": [{"date": "2026-10-23", "value": value}]}, self.now)["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
