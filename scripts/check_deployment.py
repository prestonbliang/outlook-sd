"""Check the public Vercel deployment without submitting reports or exposing credentials."""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.quality import quality


def check(base_url, *, allow_unavailable=False, require_reporting=False):
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("Provide a deployment origin such as https://outlook-sd.vercel.app")
    if parsed.path not in {"", "/"}:
        raise ValueError("Use the deployment origin without a path")
    base_url = base_url.rstrip("/")
    headers = {"User-Agent": "OutlookSD-deployment-check"}
    bypass = os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET")
    if bypass:
        headers["x-vercel-protection-bypass"] = bypass

    def get(path, *, json_body=False, range_request=False):
        request_headers = {**headers, **({"Range": "bytes=0-15"} if range_request else {})}
        with urlopen(Request(base_url + path, headers=request_headers), timeout=30) as response:
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
    manifest = get("/api/build.json", json_body=True)
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported deployment manifest")
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
    args = parser.parse_args()
    try:
        manifest = check(args.url, allow_unavailable=args.allow_unavailable, require_reporting=args.require_reporting)
    except Exception as error:
        # HTTP exceptions contain no request headers; do not print request objects or environment values.
        parser.exit(1, f"Deployment check failed: {error}\n")
    print(f"Deployment checked: {manifest['places']} neighborhoods; forecasts {manifest['forecast_status']}")


if __name__ == "__main__":
    main()
