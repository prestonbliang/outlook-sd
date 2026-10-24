"""Exercise the deployment checker with HTTP response fixtures, without network calls."""
import io
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from scripts.check_deployment import check


class Response(io.BytesIO):
    def __init__(self, body, *, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


class DeploymentTests(unittest.TestCase):
    def response(self, request, timeout=30):
        path = request.full_url.removeprefix("https://test.vercel.app")
        self.requests.append(request)
        if path.endswith(".pmtiles"):
            return Response(b"PMTiles\x03" + b"\0" * 8, status=self.range_status,
                            headers={"Content-Range": "bytes 0-15/1000"})
        if not path.endswith(".json"):
            return Response(b"<html>Outlook SD</html>")
        if path == "/api/build.json":
            body = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
                    "places": 1, "forecast_status": self.forecast_status}
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


if __name__ == "__main__":
    unittest.main()
