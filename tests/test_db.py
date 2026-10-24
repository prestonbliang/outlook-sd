"""Forecast log invariants; no source downloads or model dependencies required."""
import sqlite3
import unittest

from pipeline import db


class ForecastLogTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.executescript(db.SCHEMA)
        self.row = {"unit_id": "test", "target_date": "2026-10-24", "lead_days": 0,
                    "value": .2, "level": "low"}

    def tearDown(self):
        self.con.close()

    def test_retry_preserves_original_forecast_and_score_reference(self):
        db.log_forecasts(self.con, "run-1", "water", [self.row], "model-1")
        forecast_id = self.con.execute("select id from forecasts").fetchone()[0]
        self.con.execute("insert into scores values (?, 0, 'meets', 1, 'scored')", (forecast_id,))
        db.log_forecasts(self.con, "run-1", "water", [{**self.row, "value": .9}], "model-2")
        self.assertEqual(self.con.execute("select id, value from forecasts").fetchall(), [(forecast_id, .2)])
        self.assertEqual(self.con.execute("select count(*) from scores join forecasts on forecasts.id=scores.forecast_id").fetchone()[0], 1)

    def test_new_issue_keeps_both_forecasts(self):
        for run in ["run-1", "run-2"]:
            db.log_forecasts(self.con, run, "water", [self.row], "model-1")
        self.assertEqual(self.con.execute("select count(*) from forecasts").fetchone()[0], 2)

    def test_failed_fetch_keeps_last_success_and_records_error(self):
        db.set_status(self.con, "airnow", "attempt-1", success="success-1", newest="data-1")
        db.set_status(self.con, "airnow", "attempt-2", error="network unavailable")
        self.assertEqual(self.con.execute("select last_success, newest_data, error from source_status").fetchone(),
                         ("success-1", "data-1", "network unavailable"))
        db.set_status(self.con, "airnow", "attempt-3", success="success-3")
        self.assertIsNone(self.con.execute("select error from source_status").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
