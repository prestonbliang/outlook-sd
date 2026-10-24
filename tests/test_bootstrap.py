"""Fresh-checkout pipeline preparation must not depend on untracked helper files."""
import pandas as pd

from pipeline import history, run_all


def test_weather_points_csv_is_generated_before_archive_download(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "PROCESSED", tmp_path)
    calls = []
    monkeypatch.setattr(history.openmeteo, "fetch_history", lambda points, **kw: calls.append(points))
    history.weather()
    assert (tmp_path / "weather_points.csv").exists()
    assert calls and {"point_id", "lat", "lon"} <= set(calls[0])
    assert "g32.75_-117.25" in set(calls[0].point_id)


def test_live_weather_includes_all_air_monitor_points_without_history(tmp_path, monkeypatch):
    monkeypatch.setattr(run_all, "PROCESSED", tmp_path)
    points = set(run_all.weather_points())
    for param in ["pm25", "ozone"]:
        import json
        sites = json.loads((run_all.ART / "air" / f"sites_{param}.json").read_text())
        assert {s["point_id"] for s in sites} <= points


def test_fetch_failure_is_logged_without_stopping_other_sources(tmp_path, monkeypatch):
    from pipeline import db
    monkeypatch.setattr(db, "DB", tmp_path / "outlook.db")
    with db.connect() as con:
        def broken():
            raise RuntimeError("unreachable")
        assert run_all.run_source(con, "airnow", broken) is None
        value = run_all.run_source(con, "other", lambda: pd.DataFrame({"v": [1]}))
        assert value.v.tolist() == [1]
        assert con.execute("SELECT error FROM source_status WHERE source='airnow'").fetchone()[0]
        assert con.execute("SELECT last_success FROM source_status WHERE source='other'").fetchone()[0]
