"""API contracts use isolated fixtures and never require the historical archive."""
import json
import sqlite3

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api.main as api
from pipeline.db import SCHEMA

LEVELS = {"low", "moderate", "high", "very_high", "good", "usg", "unhealthy", "very_unhealthy", "hazardous", None}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DB", tmp_path / "outlook.db")
    monkeypatch.setattr(api, "PROCESSED", tmp_path)
    return TestClient(api.app)


def test_fresh_checkout_serves_all_endpoints(client):
    # No DB, historical data, secrets, or network calls: missing data is an explicit state.
    assert client.get("/places", params={"q": "imperial"}).json()
    for place in ["imperial-beach", "downtown", "alpine"]:
        o = client.get(f"/outlook/{place}")
        assert o.status_code == 200
        assert [t["tile"] for t in o.json()["tiles"]] == api.TILES
        for tile in api.TILES:
            h = client.get(f"/hazard/{tile}", params={"place_id": place})
            assert h.status_code == 200
            assert {"what_to_do", "window", "series", "sources"} <= set(h.json())
    assert client.get("/track-record").status_code == 200
    health = client.get("/health").json()
    assert health["sources"] and all(s["stale"] for s in health["sources"].values())
    assert not api.DB.exists()  # reading never manufactures a forecast log


def test_outlook_schema(client):
    o = client.get("/outlook", params={"lat": 32.58, "lon": -117.13}).json()
    assert {"place", "updated_at", "tiles"} <= set(o)
    for t in o["tiles"]:
        assert {"tile", "days", "reason", "factors", "official_advisory", "sources", "stale_inputs"} <= set(t)
        assert t["sources"]
        assert t["days"] == []


def test_map_dates_and_empty_layers(client):
    dates = client.get("/map/dates").json()["dates"]
    assert len(dates) == 4
    for tile in api.TILES:
        for date in dates:
            r = client.get(f"/map/{tile}", params={"date": date})
            assert r.status_code == 200
            assert r.json()["type"] == "FeatureCollection"
            assert r.json()["features"] == []
            assert r.json()["date"] == date
    assert client.get("/map/water?date=1990-01-01").status_code == 422
    assert client.get("/map/water?date=invalid").status_code == 422


def test_unknown_inputs(client):
    assert client.get("/hazard/nope?place_id=imperial-beach").status_code == 404
    assert client.get("/hazard/water?place_id=nowhere").status_code == 404
    assert client.get("/map/nope").status_code == 404
    assert client.get("/outlook/nowhere").status_code == 404


def test_map_days_stay_distinct_across_daylight_saving(client, monkeypatch):
    timestamp = pd.Timestamp
    class FixedTimestamp:
        @staticmethod
        def now(tz=None):
            return timestamp("2026-11-01 00:00", tz=tz)
    monkeypatch.setattr(api.pd, "Timestamp", FixedTimestamp)
    assert client.get("/map/dates").json()["dates"] == ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"]


def seed_water(date):
    with sqlite3.connect(api.DB) as con:
        con.executescript(SCHEMA)
        station = next(iter(api.water_stations()))
        con.execute("INSERT INTO forecasts (run_ts, tile, unit_id, target_date, lead_days, value, level, factors_json, extra_json) "
                    "VALUES (?, 'water', ?, ?, 0, 0.7, 'high', '[]', '{}')",
                    (pd.Timestamp.now(tz="UTC").isoformat(), station, date))


def test_expired_forecasts_do_not_reappear_as_today(client):
    yesterday = str((pd.Timestamp.now(tz=api.TZ) - pd.Timedelta(days=1)).date())
    seed_water(yesterday)
    assert api.latest("water").empty
    assert client.get("/map/water").json()["features"] == []


def test_selected_forecast_date_is_respected(client):
    date = client.get("/map/dates").json()["dates"][1]
    seed_water(date)
    tomorrow = client.get(f"/map/water?date={date}").json()
    assert len(tomorrow["features"]) == 1
    assert tomorrow["features"][0]["properties"]["value"] == .7
    assert client.get("/map/water").json()["features"] == []


def test_cached_heat_geometry_cannot_keep_an_old_rating(client):
    (api.PROCESSED / "map_heat.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []},
         "properties": {"zip": "92101", "level": "low", "value": 0, "chs": 0, "source": "outlook"}}
    ]}))
    properties = client.get("/map/heat").json()["features"][0]["properties"]
    assert properties == {"zip": "92101"}


def test_forecast_window_does_not_bridge_missing_days(client):
    assert api.window([{"date": "2026-10-24", "verdict": "Low"}, {"date": "2026-10-26", "verdict": "Low"}]) == {
        "verdict": "Low", "through": "2026-10-24"}


def test_optional_fire_feeds_are_not_required_weather_inputs(client):
    status = {name: {"stale": True} for name in api.STALE_HOURS}
    status["openmeteo"] = {"stale": False}
    assert api.stale_inputs("fire", status) == []
    status["openmeteo"] = {"stale": True}
    assert "Open-Meteo weather" in api.stale_inputs("fire", status)


def test_artifact_cache_returns_independent_objects(client):
    first = api.artifact("water", "thresholds.json")
    first["test_mutation"] = True
    assert "test_mutation" not in api.artifact("water", "thresholds.json")


def test_air_fallback_ignores_malformed_observations(client, monkeypatch):
    monkeypatch.setattr(api, "read_parquet", lambda name: pd.DataFrame([
        {"Latitude": "bad", "Longitude": -117.12, "AQI": 500, "SiteName": "Bad location"},
        {"Latitude": 32.58, "Longitude": -117.12, "AQI": "missing", "SiteName": "Bad AQI"},
        {"Latitude": "32.58", "Longitude": "-117.12", "AQI": "42", "SiteName": "Valid site"},
    ]).assign(ts_utc="2026-10-24T15:00:00Z", Parameter="PM2.5"))
    tile = api.air_tile(api.place_by_id("imperial-beach"), {})
    assert tile["current"]["aqi"] == 42
    assert tile["current"]["site"] == "Valid site"


def test_official_alerts_remain_visible_without_model_forecasts(client, monkeypatch):
    monkeypatch.setattr(api, "nws_alerts", lambda events: [{"headline": "Official warning"}])
    for tile in ["flood", "fire"]:
        result = api.BUILDERS[tile](api.place_by_id("imperial-beach"), {"nws": {"stale": False}})
        assert result["days"] == []
        assert result["official_advisory"]["active"] is True
        assert result["official_advisory"]["headline"] == "Official warning"


def test_stale_alert_feed_cannot_confirm_or_clear_an_alert(client):
    for alerts in [[], [{"headline": "Old warning"}]]:
        assert api.alert_status(alerts, {"nws": {"stale": True}})["active"] is None
    assert api.alert_status([], {"nws": {"stale": False}})["active"] is False


def test_water_chart_history_uses_pacific_dates_not_server_timezone(client, monkeypatch):
    timestamp = pd.Timestamp
    class FixedTimestamp:
        @staticmethod
        def now(tz=None):
            now = timestamp("2026-10-24T01:00:00Z")  # Oct 23 in San Diego, Oct 24 on a UTC server.
            return now.tz_convert(tz) if tz else now.tz_localize(None)
    monkeypatch.setattr(api.pd, "Timestamp", FixedTimestamp)
    seed_water("2026-10-22")
    seed_water("2026-10-23")
    station = next(iter(api.water_stations()))
    assert [p["t"] for p in api.series_water(station)["observed"]] == ["2026-10-22"]


def test_stale_incidents_are_not_shown_as_current_map_markers(client, monkeypatch):
    incidents = pd.DataFrame([{"Latitude": 32.7, "Longitude": -117.1, "Name": "Old incident",
                               "AcresBurned": 10, "PercentContained": 0}])
    monkeypatch.setattr(api, "read_parquet", lambda name: incidents if name == "calfire_active" else None)
    monkeypatch.setattr(api, "source_status", lambda: {"calfire": {"stale": True}})
    result = api.map_layer("fire")
    assert result["features"] == []
    assert "older incident markers are hidden" in result["context_notice"]
    monkeypatch.setattr(api, "source_status", lambda: {"calfire": {"stale": False}})
    assert api.map_layer("fire")["features"][0]["properties"]["active_fire"] is True


def test_track_record_with_fire_scores_that_have_no_hit(client):
    # Fire is scored county-wide (expected vs observed count) with hit = NULL; SUM(hit) must not crash the log.
    with sqlite3.connect(api.DB) as con:
        con.executescript(SCHEMA)
        con.execute("INSERT INTO forecasts (id, run_ts, tile, unit_id, target_date, lead_days, value, level, factors_json, "
                    "extra_json) VALUES (1, '2026-10-23T00:00:00+00:00', 'fire', 'county', '2026-10-23', 0, 0.2, NULL, '[]', '{}')")
        con.execute("INSERT INTO scores VALUES (1, 1.0, NULL, NULL, '2026-10-24T00:00:00+00:00')")
    live = client.get("/track-record").json()["tiles"]["fire"]["live"]
    assert live["hits"] == 0 and live["observed_fires"] == 1 and live["expected_fires"] == 0.2
