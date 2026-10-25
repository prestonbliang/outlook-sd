"""Read-only setup diagnosis. Prints availability, never key values. No dependencies needed."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = dict(os.environ)
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            try:
                tokens = shlex.split(value, comments=True)
                env.setdefault(key.strip(), tokens[0] if tokens else "")
            except ValueError:
                print("Invalid quoting in .env; correct it before running the app.")
                return 1
    checks = []

    def check(label, ok, next_step):
        checks.append(ok)
        print(f"{'OK' if ok else 'NEEDED'}: {label}" + ("" if ok else f" — {next_step}"))

    check("Python 3.12+", sys.version_info >= (3, 12), "install Python 3.12 or newer")
    check("uv", bool(shutil.which("uv")), "install uv from docs.astral.sh/uv")
    for module in ["pandas", "fastapi", "lightgbm", "geopandas", "pyarrow", "pytest"]:
        check(f"Python dependency {module}", importlib.util.find_spec(module) is not None, "run uv sync")
    for binary in ["node", "npm"]:
        check(binary, bool(shutil.which(binary)), "install Node 22 and npm")
    check("Web dependencies", (ROOT / "web/node_modules/next/package.json").exists(), "cd web && npm ci")
    check("Shared .env", env_file.exists(), "copy .env.example to .env and configure your services")
    for name, service in [("AIRNOW_API_KEY", "AirNow live forecasts"), ("FIRMS_MAP_KEY", "NASA satellite detections"),
                          ("NEXT_PUBLIC_SUPABASE_URL", "Community reporting URL")]:
        check(service, bool(env.get(name)), f"configure {name} in .env")
    check("Community reporting public key", bool(env.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY") or
                                                env.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")),
          "configure NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY (or legacy NEXT_PUBLIC_SUPABASE_ANON_KEY) in .env")
    for name, task in [("zcta_sd.parquet", "geo"), ("coastal_places.parquet", "geo"), ("acs_zcta.parquet", "acs"),
                       ("ems_daily_zip.parquet", "ems"), ("beach_results.parquet", "beachwatch"),
                       ("ibwc_flow.parquet", "ibwc"), ("cdip_191.parquet", "cdip"), ("tides_9410170.parquet", "tides")]:
        check(name, (ROOT / "data/processed" / name).exists(), f"make history SOURCES={task}, or restore state")
    check("Forecast log", (ROOT / "data/outlook.db").exists(), "make refresh after restoring/building source data")
    check("Static API", (ROOT / "web/public/api/places.json").exists(), "make init (empty states) or make refresh (live)")
    check("San Diego basemap", (ROOT / "web/public/tiles/sandiego.pmtiles").is_file(), "restore the repository basemap asset")
    schema = (ROOT / "supabase/schema.sql").read_text()
    places = json.loads((ROOT / "api/places.json").read_text())
    check("Reporting neighborhood list", all(f"('{p['id']}'," in schema for p in places),
          "run python scripts/sync_report_places.py and reapply supabase/schema.sql")
    print("\nSupabase schema installation and deployment secrets must also be checked in their service dashboards.")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
