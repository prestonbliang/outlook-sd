"""API contract tests against the brief (§5): /places, /outlook, /hazard, /map, /track-record, /health."""
import pytest
from fastapi.testclient import TestClient

from api.main import DB, TILES, VERDICTS, app

LEVELS = {"low", "moderate", "high", "very_high", "good", "usg", "unhealthy", "very_unhealthy", "hazardous", None}
pytestmark = pytest.mark.skipif(not DB.exists(), reason="no forecast log yet (run python -m pipeline.run_all)")
c = TestClient(app)


def test_places():
    r = c.get("/places", params={"q": "imperial"}).json()
    assert r and {"id", "name", "zip", "lat", "lon"} <= set(r[0])


@pytest.mark.parametrize("lat,lon", [(32.58, -117.13), (32.85, -117.27)])
def test_outlook_schema(lat, lon):
    o = c.get("/outlook", params={"lat": lat, "lon": lon}).json()
    assert {"place", "updated_at", "tiles"} <= set(o)
    assert [t["tile"] for t in o["tiles"]] == TILES
    for t in o["tiles"]:
        assert {"tile", "days", "reason", "factors", "official_advisory", "sources", "stale_inputs"} <= set(t)
        assert t["sources"], f"{t['tile']} has no data source"
        for d in t["days"]:
            assert {"date", "level", "value", "verdict"} <= set(d)
            assert d["level"] in LEVELS
            assert d["verdict"] in VERDICTS[t["tile"]].values()  # verdicts only from the fixed table


def test_hazard_detail():
    for tile in TILES:
        h = c.get(f"/hazard/{tile}", params={"place_id": "imperial-beach"})
        assert h.status_code == 200
        assert {"what_to_do", "window", "series", "sources"} <= set(h.json())
    assert c.get("/hazard/nope", params={"place_id": "imperial-beach"}).status_code == 404
    assert c.get("/hazard/water", params={"place_id": "nowhere"}).status_code == 404


def test_map_is_geojson():
    for tile in TILES:
        m = c.get(f"/map/{tile}").json()
        assert m["type"] == "FeatureCollection" and isinstance(m["features"], list)


def test_track_record_and_health():
    tr = c.get("/track-record").json()
    assert set(tr["tiles"]) == set(TILES)
    h = c.get("/health").json()
    assert all("stale" in v for v in h["sources"].values())
