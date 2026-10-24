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
