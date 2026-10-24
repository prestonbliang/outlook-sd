"""Render every API response to static JSON (web/public/api/...) via TestClient — same code path as the live API.
Usage: python -m api.export [out_dir]"""
import json
import shutil
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from api.main import PLACES, ROOT, TILES, app


def main(out=ROOT / "web" / "public" / "api"):
    out = Path(out)
    tmp = out.with_name(out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    c = TestClient(app)

    def put(path, url):
        r = c.get(url)
        r.raise_for_status()
        f = tmp / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(r.json(), separators=(",", ":")))

    put("places.json", "/places")
    put("track-record.json", "/track-record")
    put("health.json", "/health")
    put("map/dates.json", "/map/dates")
    dates = c.get("/map/dates").json()["dates"]
    for t in TILES:
        put(f"map/{t}.json", f"/map/{t}")
        for date in dates:
            put(f"map/{t}-{date}.json", f"/map/{t}?date={date}")
    for p in PLACES:
        put(f"outlook/{p['id']}.json", f"/outlook/{p['id']}")
        for t in TILES:
            put(f"hazard/{t}/{p['id']}.json", f"/hazard/{t}?place_id={p['id']}")
    # Public deployment metadata contains no keys or raw community observations.
    from api.snapshot import manifest
    (tmp / "build.json").write_text(json.dumps(manifest(tmp, datetime.now(timezone.utc), os.environ.get("GITHUB_SHA")),
                                               separators=(",", ":")))
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)  # swap in one step so a deploy never sees a half-written tree
    print(f"exported {sum(1 for _ in out.rglob('*.json'))} files to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
