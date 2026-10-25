"""Withdrawn/moderated observations must leave the next historical snapshot too."""
from unittest.mock import Mock

import pandas as pd
import pytest

from pipeline.sources import reports


@pytest.mark.parametrize("response", [[], [{"place_id": "alpine", "hazard": "air", "kind": "air_dust",
                                        "day": "2026-10-24", "n": 1}]])
def test_successful_refresh_replaces_absent_counts(monkeypatch, tmp_path, response):
    monkeypatch.setattr(reports, "PROCESSED", tmp_path)
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://reports.example.invalid")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    old = pd.DataFrame([
        {"place_id": "alpine", "hazard": "heat", "kind": "heat_shade", "day": "2000-01-01", "n": 2},
        {"place_id": "alpine", "hazard": "heat", "kind": "heat_shade",
         "day": str(pd.Timestamp.now(tz="America/Los_Angeles").date()), "n": 3},
    ])
    path = tmp_path / "community_reports.parquet"
    old.to_parquet(path)
    monkeypatch.setattr(reports.requests, "post", Mock(return_value=Mock(status_code=200, json=lambda: response)))
    result = reports.fetch_live()
    assert not ((result.kind == "heat_shade") & (result.day != "2000-01-01")).any()
    assert result[result.day == "2000-01-01"].n.sum() == 2
    assert len(result[result.kind == "air_dust"]) == len(response)
    pd.testing.assert_frame_equal(pd.read_parquet(path), result)


def test_failed_refresh_preserves_existing_counts(monkeypatch, tmp_path):
    monkeypatch.setattr(reports, "PROCESSED", tmp_path)
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://reports.example.invalid")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    path = tmp_path / "community_reports.parquet"
    path.write_bytes(b"existing snapshot")
    monkeypatch.setattr(reports.requests, "post", Mock(return_value=Mock(status_code=503, text="Unavailable")))
    with pytest.raises(RuntimeError, match="HTTP 503"):
        reports.fetch_live()
    assert path.read_bytes() == b"existing snapshot"


@pytest.mark.parametrize("response", [{}, [None], [{"place_id": "alpine", "hazard": "air", "kind": "air_dust",
                        "day": "2026-10-24", "n": -1}], [{"place_id": "alpine", "hazard": "air", "kind": "fire_smoke",
                        "day": "2026-10-24", "n": 1}]])
def test_malformed_success_does_not_erase_existing_history(monkeypatch, tmp_path, response):
    monkeypatch.setattr(reports, "PROCESSED", tmp_path)
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://reports.example.invalid")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    path = tmp_path / "community_reports.parquet"
    path.write_bytes(b"existing snapshot")
    monkeypatch.setattr(reports.requests, "post", Mock(return_value=Mock(status_code=200, json=lambda: response)))
    with pytest.raises(RuntimeError, match="malformed aggregate"):
        reports.fetch_live()
    assert path.read_bytes() == b"existing snapshot"
