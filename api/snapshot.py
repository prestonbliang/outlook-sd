"""Deployment metadata for exported forecasts. Standard library only."""
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo


def manifest(directory, now, commit=None):
    today = now.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
    counts = {tile: 0 for tile in ["water", "air", "heat", "flood", "fire"]}
    places = json.loads((directory / "places.json").read_text())
    for place in places:
        outlook = json.loads((directory / "outlook" / f"{place['id']}.json").read_text())
        for tile in outlook["tiles"]:
            run = tile.get("run_ts")
            try:
                age = (now - datetime.fromisoformat(run.replace("Z", "+00:00"))).total_seconds() if run else None
            except (TypeError, ValueError):
                age = None
            if age is not None and -300 <= age <= 6 * 3600 and any(
                d.get("date") == today and d.get("value") is not None for d in tile["days"]
            ):
                counts[tile["tile"]] += 1
    return {"schema_version": 1, "generated_at": now.isoformat(), "forecast_date": today,
            "source_commit": commit, "places": len(places), "forecast_places": counts,
            "forecast_status": "ready" if any(counts.values()) else "unavailable",
            "reporting_configured": bool(os.environ.get("NEXT_PUBLIC_SUPABASE_URL") and
                                         os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY"))}
