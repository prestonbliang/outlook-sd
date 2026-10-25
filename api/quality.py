"""Forecast availability metadata. No model inference or third-party dependencies."""
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def quality(tile, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
    if tile.get("status") == "not_applicable":
        return {"state": "not_applicable", "forecast_date": today, "available_dates": []}
    days = tile.get("days", [])
    dates = [d["date"] for d in days if isinstance(d.get("value"), (int, float))
             and not isinstance(d["value"], bool) and math.isfinite(d["value"])]
    state = "unavailable"
    if today in dates:
        try:
            run = datetime.fromisoformat(tile.get("run_ts", "").replace("Z", "+00:00"))
            age = (now - run).total_seconds()
        except (TypeError, ValueError, AttributeError):
            age = None
        max_age = 26 * 3600 if tile.get("model") == "calheatscore" else 6 * 3600
        checks = tile.get("source_checks", [])
        inputs_current = isinstance(checks, list)
        for check in checks if isinstance(checks, list) else []:
            try:
                source_age = (now - datetime.fromisoformat(check["reference_at"].replace("Z", "+00:00"))).total_seconds()
                limit = check["max_age_hours"]
                if not isinstance(limit, (int, float)) or isinstance(limit, bool) or not math.isfinite(limit) or limit <= 0 or not -300 <= source_age <= limit * 3600:
                    inputs_current = False
            except (KeyError, TypeError, ValueError, AttributeError):
                inputs_current = False
        state = "current" if age is not None and -300 <= age <= max_age and inputs_current and not tile.get("stale_inputs") else "stale"
    return {"state": state, "forecast_date": today, "available_dates": dates}
