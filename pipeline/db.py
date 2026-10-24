"""SQLite forecast log (data/outlook.db): forecasts, scores and source status."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DB = ROOT / "data" / "outlook.db"
SCHEMA = """
CREATE TABLE IF NOT EXISTS forecasts (
  id INTEGER PRIMARY KEY, run_ts TEXT, tile TEXT, unit_id TEXT, target_date TEXT, lead_days INTEGER,
  value REAL, level TEXT, factors_json TEXT, extra_json TEXT, model_version TEXT,
  UNIQUE (run_ts, tile, unit_id, target_date));
CREATE TABLE IF NOT EXISTS scores (
  forecast_id INTEGER PRIMARY KEY REFERENCES forecasts(id), observed_value REAL, observed_level TEXT,
  hit INTEGER, scored_ts TEXT);
CREATE TABLE IF NOT EXISTS place_levels (
  run_ts TEXT, place_id TEXT, hazard TEXT, target_date TEXT, level TEXT,
  PRIMARY KEY (run_ts, place_id, hazard, target_date));
CREATE TABLE IF NOT EXISTS source_status (
  source TEXT PRIMARY KEY, last_attempt TEXT, last_success TEXT, newest_data TEXT, error TEXT);
"""
# Brief §7: a source is stale when its newest data is older than this (hours)
STALE_HOURS = {"ibwc": 3, "noaa_tides": 2, "airnow": 3, "cdip": 6, "calheatscore": 26, "beachwatch": 240,
               "sd_fire_ems": 72, "firms": 24, "openmeteo": 3, "nws": 3, "calfire": 24}


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)
    return con


def log_forecasts(con, run_ts, tile, rows, model_version):
    """rows: dicts with unit_id, target_date, lead_days, value, level, factors, extra."""
    con.executemany(
        "INSERT INTO forecasts (run_ts, tile, unit_id, target_date, lead_days, value, level, "
        "factors_json, extra_json, model_version) VALUES (?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(run_ts, tile, unit_id, target_date) DO NOTHING",
        [(run_ts, tile, r["unit_id"], r["target_date"], r["lead_days"], r["value"], r["level"],
          json.dumps(r.get("factors", [])), json.dumps(r.get("extra", {})), model_version) for r in rows])
    con.commit()


def set_status(con, source, attempt, success=None, newest=None, error=None):
    con.execute(
        "INSERT INTO source_status (source, last_attempt, last_success, newest_data, error) VALUES (?,?,?,?,?) "
        "ON CONFLICT(source) DO UPDATE SET last_attempt=excluded.last_attempt, "
        "last_success=COALESCE(excluded.last_success, last_success), "
        "newest_data=COALESCE(excluded.newest_data, newest_data), error=excluded.error",
        (source, attempt, success, newest, error))
    con.commit()
