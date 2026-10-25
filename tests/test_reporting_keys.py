"""Publishable keys must not be sent as JWTs; legacy anonymous reporting remains supported."""
from unittest.mock import Mock

import pytest

from pipeline.sources import reports


@pytest.mark.parametrize("publishable,legacy,expected", [
    ("sb_publishable_test", "", "sb_publishable_test"),
    (" sb_publishable_test ", "legacy.anon.jwt", "sb_publishable_test"),
    ("  ", "legacy.anon.jwt", "legacy.anon.jwt"),
    ("", "legacy.anon.jwt", "legacy.anon.jwt"),
])
def test_count_reads_use_the_selected_public_key(monkeypatch, tmp_path, publishable, legacy, expected):
    monkeypatch.setattr(reports, "PROCESSED", tmp_path)
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://reports.example.invalid/")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", publishable)
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", legacy)
    post = Mock(return_value=Mock(status_code=200, json=lambda: []))
    monkeypatch.setattr(reports.requests, "post", post)
    assert reports.fetch_live().empty
    assert post.call_args.args[0] == "https://reports.example.invalid/rest/v1/rpc/report_counts"
    headers = post.call_args.kwargs["headers"]
    assert headers["apikey"] == expected
    if expected.startswith("sb_publishable_"):
        assert "Authorization" not in headers
    else:
        assert headers["Authorization"] == f"Bearer {expected}"


def test_no_reporting_key_stops_before_a_network_request(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://reports.example.invalid")
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", raising=False)
    post = Mock()
    monkeypatch.setattr(reports.requests, "post", post)
    with pytest.raises(RuntimeError, match="Supabase is not configured"):
        reports.fetch_live()
    post.assert_not_called()
