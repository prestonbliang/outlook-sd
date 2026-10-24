"""Forecast availability metadata. No model inference or third-party dependencies."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def quality(tile, now=None):
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()
    if tile.get("status") == "not_applicable":
        return {"state": "not_applicable", "forecast_date": today, "available_dates": []}
    days = tile.get("days", [])
    dates = [d["date"] for d in days if d.get("value") is not None]
    state = "unavailable"
    if today in dates:
        try:
            run = datetime.fromisoformat(tile.get("run_ts", "").replace("Z", "+00:00"))
            age = (now - run).total_seconds()
        except (TypeError, ValueError, AttributeError):
            age = None
        max_age = 26 * 3600 if tile.get("model") == "calheatscore" else 6 * 3600
        state = "current" if age is not None and -300 <= age <= max_age and not tile.get("stale_inputs") else "stale"
    return {"state": state, "forecast_date": today, "available_dates": dates}
