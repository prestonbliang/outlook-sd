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


def test_heat_map_checks_state_source_when_its_ratings_are_used(client, monkeypatch):
    date = client.get("/map/dates").json()["dates"][0]
    (api.PROCESSED / "map_heat.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}, "properties": {"zip": "92011"}}
    ]}))
    pd.DataFrame({"zip": ["92011"], "issued": [date], "target_date": [date], "chs": [2]}).to_parquet(api.PROCESSED / "calheatscore_log.parquet")
    monkeypatch.setattr(api, "source_status", lambda: {"openmeteo": {"stale": False}, "calheatscore": {"stale": True}})
    layer = client.get("/map/heat").json()
    assert layer["features"][0]["properties"]["source"] == "calheatscore"
    assert "CalHeatScore" in layer["stale_inputs"]
    assert any(check["name"] == "CalHeatScore" for check in layer["source_checks"])


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


def test_odor_record_only_for_south_bay_and_counts_last_30_days(client):
    pd.DataFrame({"record": ["a", "b", "c", "d"], "zip": ["91932", "91932", "92154", "92101"],
                  "date": pd.to_datetime(["2026-10-21", "2026-09-01", "2026-10-10", "2026-10-20"]).date,
                  "city": "x", "outcome": "x", "tz_source": "x"}).to_parquet(api.PROCESSED / "odor_complaints.parquet")
    assert api.odor_reports(api.place_by_id("downtown")) is None
    o = api.odor_reports(api.place_by_id("imperial-beach"))
    assert (o["here"], o["south_bay"], o["last_here"], o["through"]) == (1, 2, "2026-10-21", "2026-10-21")


def test_cool_zones_are_sorted_by_distance_and_blank_fields_are_null(client):
    pd.DataFrame({"name": ["Far", "Near"], "address": ["1 A St", "2 B St"], "city": "San Diego", "zip": "92101",
                  "phone": ["", "619"], "pets": [None, "Service Animals Only"], "hours": ["", "Mon 10-6"],
                  "lat": [33.2, 32.72], "lon": [-117.2, -117.16]}).to_parquet(api.PROCESSED / "cool_zones.parquet")
    z = api.cool_zones_near(api.place_by_id("downtown"))
    assert [x["name"] for x in z] == ["Near", "Far"]
    assert z[1]["phone"] is None and z[1]["hours"] is None and z[0]["phone"] == "619"


def test_scenarios_without_artifacts_is_an_explicit_empty_state(client, monkeypatch):
    monkeypatch.setattr(api, "artifact", lambda tile, name: None)
    assert client.get("/scenarios").json() == {"flow": None, "sea_level": None}


def test_parquet_cache_is_invalidated_and_cannot_be_modified_by_a_caller(client, monkeypatch):
    path = api.PROCESSED / "cache_test.parquet"
    pd.DataFrame({"value": [1]}).to_parquet(path)
    from unittest.mock import Mock
    read = Mock(wraps=pd.read_parquet)
    monkeypatch.setattr(api.pd, "read_parquet", read)
    first = api.read_parquet("cache_test")
    first.loc[0, "value"] = 99
    assert first.value.iloc[0] == 99
    assert api.read_parquet("cache_test").value.iloc[0] == 1
    assert read.call_count == 1
    pd.DataFrame({"value": [2]}).to_parquet(path)
    assert api.read_parquet("cache_test").value.iloc[0] == 2
    assert read.call_count == 2


def test_query_observes_wal_commits_and_returns_independent_frames(client):
    with sqlite3.connect(api.DB) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("CREATE TABLE cache_test (value INTEGER)")
        writer.execute("INSERT INTO cache_test VALUES (1)")
        writer.commit()
        first = api.query("SELECT * FROM cache_test")
        first.loc[0, "value"] = 99
        assert first.value.iloc[0] == 99
        assert api.query("SELECT * FROM cache_test").value.tolist() == [1]
        writer.execute("INSERT INTO cache_test VALUES (2)")
        writer.commit()
        assert api.query("SELECT * FROM cache_test").value.tolist() == [1, 2]


def test_sources_expose_expiry_metadata_for_a_static_browser(client):
    now = pd.Timestamp.now(tz="UTC").isoformat()
    with sqlite3.connect(api.DB) as con:
        con.executescript(SCHEMA)
        con.execute("INSERT INTO source_status VALUES ('openmeteo', ?, ?, NULL, NULL)", (now, now))
    status = client.get("/health").json()["sources"]["openmeteo"]
    assert status["reference_at"] == now and status["max_age_hours"] == 3 and status["stale"] is False
    for tile in client.get("/outlook/downtown").json()["tiles"]:
        assert tile["source_checks"]


def test_partial_scenario_artifact_does_not_crash_with_river_history(client, monkeypatch):
    monkeypatch.setattr(api, "artifact", lambda tile, name: {"flow": None, "sea_level": {"period": "Historical"}})
    pd.DataFrame({"ts_utc": pd.to_datetime(["2026-10-24T00:00:00Z"]), "discharge_m3s": [1.0]}).to_parquet(api.PROCESSED / "ibwc_flow.parquet")
    response = client.get("/scenarios")
    assert response.status_code == 200 and response.json()["flow"] is None


def test_state_heat_issue_dates_use_the_same_pacific_midnight_as_the_forecast(client):
    now = pd.Timestamp.now(tz="UTC")
    issued = now.tz_convert(api.TZ).normalize().tz_localize(None)
    with sqlite3.connect(api.DB) as con:
        con.executescript(SCHEMA)
        con.execute("INSERT INTO source_status VALUES ('calheatscore', ?, ?, ?, NULL)",
                    (now.isoformat(), now.isoformat(), str(issued)))
    check = api.source_status()["calheatscore"]
    assert check["reference_at"] == issued.tz_localize(api.TZ).tz_convert("UTC").isoformat()
    assert check["stale"] is False


def test_detail_carries_dated_advice_when_forecast_levels_change(client, monkeypatch):
    dates = client.get("/map/dates").json()["dates"]
    def fake_heat(place, status):
        tile = api.empty_tile("heat", "Test record", status)
        tile.update(model="calheatscore", days=[{"date": dates[0], "value": 0, "level": "low", "verdict": "Low"},
                                               {"date": dates[1], "value": 3, "level": "high", "verdict": "High"}])
        return tile
    monkeypatch.setitem(api.BUILDERS, "heat", fake_heat)
    response = client.get("/hazard/heat?place_id=imperial-beach").json()
    assert response["what_to_do_by_date"][dates[0]] == api.ACTIONS["heat"]["low"]
    assert response["what_to_do_by_date"][dates[1]] == api.ACTIONS["heat"]["high"]
