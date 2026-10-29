"""Exercise the deployment checker with HTTP response fixtures, without network calls."""
import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from scripts.check_deployment import check


class Response(io.BytesIO):
    def __init__(self, body, *, status=200, headers=None, url="https://test.vercel.app"):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}
        self.url = url

    def geturl(self):
        return self.url


class DeploymentTests(unittest.TestCase):
    def response(self, request, timeout=30):
        path = urlsplit(request.full_url).path
        self.requests.append(request)
        if path.endswith(".pmtiles"):
            return Response(b"PMTiles\x03" + b"\0" * 8, status=self.range_status,
                            headers={"Content-Range": "bytes 0-15/1000"})
        if not path.endswith(".json"):
            return Response(b"<html>Outlook SD</html>")
        if path == "/api/build.json":
            body = {"schema_version": 1, "generated_at": self.generated_at, "source_commit": self.source_commit,
                    "places": 1, "forecast_status": self.forecast_status}
            if self.manifests:
                result = self.manifests.pop(0)
                if isinstance(result, Exception):
                    raise result
                body.update(result)
        elif path == "/app-build.json":
            body = {"schema_version": 1, "reporting": self.reporting}
        elif path == "/api/scenarios.json":
            body = {"flow": None, "sea_level": None}
        elif path.startswith("/api/outlook/"):
            now = datetime.now(timezone.utc)
            from zoneinfo import ZoneInfo
            body = {"tiles": [{"run_ts": now.isoformat() if not self.expired else "2020-01-01T00:00:00Z",
                                "days": [{"date": now.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat(), "value": 1}]}]}
        elif path == "/api/places.json":
            body = [{"id": "test-place"}]
        elif "/map/" in path:
            body = {"type": "FeatureCollection", "features": []}
        else:
            body = {}
        return Response(json.dumps(body).encode(), headers={"Content-Type": "application/json"})

    def setUp(self):
        self.requests = []
        self.forecast_status = "ready"
        self.range_status = 206
        self.reporting = "configured"
        self.expired = False
        self.generated_at = datetime.now(timezone.utc).isoformat()
        self.source_commit = "f" * 40
        self.manifests = []

    def poll_snapshot(self, *, attempts=3):
        return check("https://test.vercel.app", expected_build={
            "source_commit": self.source_commit, "generated_at": self.generated_at,
        }, snapshot_attempts=attempts, retry_delay=10)

    def manifest_requests(self):
        return [request for request in self.requests if urlsplit(request.full_url).path == "/api/build.json"]

    def test_checks_static_pages_api_and_range_support_with_get_only(self):
        with patch("scripts.check_deployment.urlopen", self.response):
            result = check("https://test.vercel.app")
        self.assertEqual(result["forecast_status"], "ready")
        self.assertTrue(all(r.get_method() == "GET" for r in self.requests))
        self.assertEqual(self.requests[-1].get_header("Range"), "bytes=0-15")

    def test_unavailable_forecasts_require_an_explicit_initial_launch(self):
        self.forecast_status = "unavailable"
        with patch("scripts.check_deployment.urlopen", self.response):
            with self.assertRaisesRegex(ValueError, "no recent live forecasts"):
                check("https://test.vercel.app")
            self.assertEqual(check("https://test.vercel.app", allow_unavailable=True)["forecast_status"], "unavailable")

    def test_map_without_byte_ranges_fails_the_check(self):
        self.range_status = 200
        with patch("scripts.check_deployment.urlopen", self.response):
            with self.assertRaisesRegex(ValueError, "expected HTTP 206"):
                check("https://test.vercel.app")

    def test_rejects_non_web_origins_and_paths(self):
        for url in ["file:///etc/passwd", "https://test.vercel.app/map", "https://test.vercel.app/?token=value"]:
            with self.assertRaises(ValueError):
                check(url)

    def test_reporting_requirement_detects_missing_vercel_variables(self):
        self.reporting = "unconfigured"
        with patch("scripts.check_deployment.urlopen", self.response):
            with self.assertRaisesRegex(ValueError, "public Vercel variables"):
                check("https://test.vercel.app", require_reporting=True)

    def test_fresh_build_cannot_claim_that_expired_forecasts_are_current(self):
        self.expired = True
        with patch("scripts.check_deployment.urlopen", self.response):
            with self.assertRaisesRegex(ValueError, "expired since publication"):
                check("https://test.vercel.app")

    def test_public_domain_must_serve_the_exact_snapshot_just_built(self):
        expected = {"source_commit": self.source_commit, "generated_at": self.generated_at}
        with patch("scripts.check_deployment.urlopen", self.response):
            self.assertEqual(check("https://test.vercel.app", expected_build=expected)["source_commit"], self.source_commit)
            for field, wrong_value in [("source_commit", "0" * 40), ("generated_at", "2020-01-01T00:00:00Z")]:
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, f"Published {field}"):
                    check("https://test.vercel.app", expected_build={**expected, field: wrong_value})

    def test_protected_url_explains_authentication_instead_of_misdiagnosing_the_app(self):
        with patch("scripts.check_deployment.urlopen", lambda *args, **kw: Response(b"Login", url="https://vercel.com/login")):
            with self.assertRaisesRegex(ValueError, "redirects to Vercel authentication"):
                check("https://test.vercel.app")

    def test_polls_until_alias_serves_exact_commit_and_timestamp(self):
        self.manifests = [{"source_commit": "0" * 40}, {"generated_at": "2020-01-01T00:00:00Z"}, {}]
        with patch("scripts.check_deployment.urlopen", self.response), patch("scripts.check_deployment.time.sleep") as sleep:
            self.assertEqual(self.poll_snapshot()["generated_at"], self.generated_at)
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_called_with(10)
        requests = self.manifest_requests()
        self.assertEqual(len(requests), 3)
        self.assertEqual(len({request.full_url for request in requests}), 3)
        self.assertTrue(all("_outlook_check=" in request.full_url for request in requests))
        self.assertTrue(all(request.get_header("Cache-control") == "no-cache" for request in requests))

    def test_persistent_mismatch_still_fails_after_bounded_attempts(self):
        self.manifests = [{"generated_at": "2020-01-01T00:00:00Z"}] * 3
        with patch("scripts.check_deployment.urlopen", self.response), patch("scripts.check_deployment.time.sleep") as sleep:
            with self.assertRaisesRegex(ValueError, "Published generated_at.*expected.*received"):
                self.poll_snapshot()
        self.assertEqual(len(self.manifest_requests()), 3)
        self.assertEqual(sleep.call_count, 2)

    def test_retries_only_transient_manifest_http_and_network_errors(self):
        for failure in [HTTPError("https://test.vercel.app", code, "temporary", {}, None)
                        for code in (404, 429, 500, 502, 503, 504)] + [URLError("connection reset"), TimeoutError()]:
            with self.subTest(failure=failure):
                self.requests = []
                self.manifests = [failure, {}]
                with patch("scripts.check_deployment.urlopen", self.response), patch("scripts.check_deployment.time.sleep") as sleep:
                    self.poll_snapshot()
                self.assertEqual(len(self.manifest_requests()), 2)
                sleep.assert_called_once_with(10)

    def test_persistent_network_failure_is_not_reported_as_success(self):
        self.manifests = [URLError("unreachable")] * 3
        with patch("scripts.check_deployment.urlopen", self.response), patch("scripts.check_deployment.time.sleep") as sleep:
            with self.assertRaises(URLError):
                self.poll_snapshot()
        self.assertEqual(sleep.call_count, 2)

    def test_authentication_errors_are_not_retried(self):
        self.manifests = [HTTPError("https://test.vercel.app", 403, "forbidden", {}, None)]
        with patch("scripts.check_deployment.urlopen", self.response), patch("scripts.check_deployment.time.sleep") as sleep:
            with self.assertRaises(HTTPError):
                self.poll_snapshot()
        sleep.assert_not_called()

    def test_matching_manifest_does_not_mask_broken_map_or_expired_forecasts(self):
        for broken_map in (False, True):
            with self.subTest(broken_map=broken_map):
                self.expired = not broken_map
                self.range_status = 200 if broken_map else 206
                with patch("scripts.check_deployment.urlopen", self.response), patch("scripts.check_deployment.time.sleep") as sleep:
                    with self.assertRaisesRegex(ValueError, "HTTP 206" if broken_map else "expired since publication"):
                        self.poll_snapshot()
                sleep.assert_not_called()

    def test_invalid_manifest_fails_immediately(self):
        self.manifests = [{"schema_version": 99}]
        with patch("scripts.check_deployment.urlopen", self.response), patch("scripts.check_deployment.time.sleep") as sleep:
            with self.assertRaisesRegex(ValueError, "Unsupported deployment manifest"):
                self.poll_snapshot()
        sleep.assert_not_called()

    def test_invalid_poll_configuration_or_expected_build_fails_before_network(self):
        with patch("scripts.check_deployment.urlopen") as request:
            for options in [{"snapshot_attempts": 0}, {"snapshot_attempts": 14},
                            {"retry_delay": -1}, {"retry_delay": 31}, {"expected_build": {}}]:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    check("https://test.vercel.app", **options)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
