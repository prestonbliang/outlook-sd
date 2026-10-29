"""Check the public Vercel deployment without submitting reports or exposing credentials."""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.quality import quality


def check(base_url, *, allow_unavailable=False, require_reporting=False, expected_build=None,
          snapshot_attempts=1, retry_delay=10):
    if not 1 <= snapshot_attempts <= 13 or not 0 <= retry_delay <= 30:
        raise ValueError("Use 1–13 snapshot attempts and a retry delay of 0–30 seconds")
    if expected_build is not None and any(not expected_build.get(field) for field in ("source_commit", "generated_at")):
        raise ValueError("Expected build must include source_commit and generated_at")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Provide a deployment origin such as https://outlook-sd.vercel.app")
    if parsed.path not in {"", "/"}:
        raise ValueError("Use the deployment origin without a path")
    base_url = base_url.rstrip("/")
    headers = {"User-Agent": "OutlookSD-deployment-check", "Cache-Control": "no-cache"}
    bypass = os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET")
    if bypass:
        headers["x-vercel-protection-bypass"] = bypass

    def get(path, *, json_body=False, range_request=False):
        request_headers = {**headers, **({"Range": "bytes=0-15"} if range_request else {})}
        with urlopen(Request(base_url + path, headers=request_headers), timeout=30) as response:
            final_url = urlparse(response.geturl()) if hasattr(response, "geturl") else None
            if final_url and final_url.hostname == "vercel.com" and final_url.path.startswith(("/login", "/sso-api")):
                raise ValueError("Deployment redirects to Vercel authentication; check the public production domain or configure VERCEL_AUTOMATION_BYPASS_SECRET")
            expected = 206 if range_request else 200
            if response.status != expected:
                raise ValueError(f"{path}: expected HTTP {expected}, got {response.status}")
            if range_request:
                if not response.headers.get("Content-Range", "").startswith("bytes 0-15/"):
                    raise ValueError("Basemap response is missing its Content-Range")
                if response.read(16)[:7] != b"PMTiles":
                    raise ValueError("Basemap response has invalid PMTiles bytes")
                return None
            if json_body:
                if "application/json" not in response.headers.get("Content-Type", ""):
                    raise ValueError(f"{path}: JSON request was served a different content type")
                return json.load(response)
            if b"Outlook SD" not in response.read():
                raise ValueError(f"{path}: did not receive the app page")
    for page in ["/", "/map/", "/data/", "/track-record/", "/what-if/", "/hazard/water/"]:
        get(page)
    configuration = get("/app-build.json", json_body=True)
    if configuration.get("schema_version") != 1 or configuration.get("reporting") not in {"configured", "unconfigured", "test"}:
        raise ValueError("Unsupported reporting configuration metadata")
    if require_reporting and configuration["reporting"] != "configured":
        raise ValueError("Community reporting is not configured in the deployed browser build; set the public Vercel variables and rebuild")
    # The production alias can still serve the previous snapshot immediately after
    # the CLI reports Ready. Poll only its manifest; never relax exact identity or
    # retry away a failed content, freshness, authentication, or map validation.
    attempts = snapshot_attempts if expected_build is not None else 1
    for attempt in range(1, attempts + 1):
        try:
            path = "/api/build.json"
            if expected_build is not None:
                path += "?_outlook_check=" + uuid4().hex
            manifest = get(path, json_body=True)
        except HTTPError as error:
            if error.code not in {404, 429, 500, 502, 503, 504} or attempt == attempts:
                raise
            pending = f"manifest returned HTTP {error.code}"
        except (URLError, TimeoutError):
            if attempt == attempts:
                raise
            pending = "manifest request temporarily unavailable"
        else:
            if manifest.get("schema_version") != 1:
                raise ValueError("Unsupported deployment manifest")
            mismatches = [field for field in ("source_commit", "generated_at")
                          if expected_build is not None and manifest.get(field) != expected_build[field]]
            if not mismatches:
                break
            pending = "; ".join(f"Published {field} does not match the snapshot just built "
                                f"(expected {expected_build[field]!r}, received {manifest.get(field)!r})"
                                for field in mismatches)
            if attempt == attempts:
                raise ValueError(pending)
        print(f"Waiting for published snapshot ({attempt}/{attempts}): {pending}; retrying in {retry_delay}s",
              file=sys.stderr)
        time.sleep(retry_delay)
    generated = datetime.fromisoformat(manifest["generated_at"].replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - generated).total_seconds()
    if not -300 <= age <= 6 * 3600:
        raise ValueError("The deployment's forecast snapshot is not recent")
    if not allow_unavailable and manifest.get("forecast_status") != "ready":
        raise ValueError("Site is reachable, but no recent live forecasts are available")
    places = get("/api/places.json", json_body=True)
    if not places or len(places) != manifest["places"]:
        raise ValueError("Neighborhood export is incomplete")
    get("/api/health.json", json_body=True)
    scenarios = get("/api/scenarios.json", json_body=True)
    if not isinstance(scenarios, dict) or not {"flow", "sea_level"} <= scenarios.keys():
        raise ValueError("Scenario export is incomplete")
    for tile in ["water", "air", "heat", "flood", "fire"]:
        layer = get(f"/api/map/{tile}.json", json_body=True)
        if layer.get("type") != "FeatureCollection":
            raise ValueError(f"Invalid {tile} layer")
    first = get(f"/api/outlook/{places[0]['id']}.json", json_body=True)
    if not allow_unavailable:
        # Build-time availability is not proof that the same sources are still fresh now.
        current = lambda payload: any(quality(tile)["state"] == "current" for tile in payload.get("tiles", []))
        found = current(first)
        for place in places[1:]:
            if found:
                break
            found = current(get(f"/api/outlook/{place['id']}.json", json_body=True))
        if not found:
            raise ValueError("Forecasts have expired since publication; refresh the source pipeline and publish a new snapshot")
    get("/tiles/sandiego.pmtiles", range_request=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--allow-unavailable", action="store_true", help="Check an explicitly requested initial launch without forecasts")
    parser.add_argument("--require-reporting", action="store_true", help="Fail when browser reporting variables were not applied to this deployment")
    parser.add_argument("--expected-build", type=Path, help="Local api/build.json to verify the exact published commit and snapshot")
    parser.add_argument("--snapshot-attempts", type=int, default=1, help="Manifest attempts while a new deployment propagates (1–13; exact identity is still required)")
    parser.add_argument("--retry-delay", type=float, default=10, help="Seconds between manifest attempts (0–30)")
    args = parser.parse_args()
    try:
        expected_build = json.loads(args.expected_build.read_text()) if args.expected_build else None
        manifest = check(args.url, allow_unavailable=args.allow_unavailable, require_reporting=args.require_reporting,
                         expected_build=expected_build, snapshot_attempts=args.snapshot_attempts, retry_delay=args.retry_delay)
    except Exception as error:
        # HTTP exceptions contain no request headers; do not print request objects or environment values.
        parser.exit(1, f"Deployment check failed: {error}\n")
    print(f"Deployment checked: {manifest['places']} neighborhoods; forecasts {manifest['forecast_status']}")


if __name__ == "__main__":
    main()
