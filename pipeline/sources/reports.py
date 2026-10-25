"""Community reports from the app (Supabase): daily counts per place, hazard and report type (no raw rows)."""
import os
import re
from datetime import date

import pandas as pd
import requests

from ._common import PROCESSED, redact
from pipeline.storage import atomic_output


def fetch_live(days=30):
    days = min(max(int(days), 1), 30)
    fetched_at = pd.Timestamp.now(tz="UTC")
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").strip().rstrip("/")
    key = (os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "").strip()
           or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "").strip())
    if not url or not key:
        raise RuntimeError("Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY or legacy anon key)")
    headers = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith("sb_publishable_"):
        headers["Authorization"] = f"Bearer {key}"
    r = requests.post(f"{url}/rest/v1/rpc/report_counts", json={"days": days}, timeout=60,
                      headers=headers)
    if r.status_code != 200:
        raise RuntimeError(redact(f"reports: HTTP {r.status_code} {r.text[:300]}"))
    rows = r.json()
    if not isinstance(rows, list):
        raise RuntimeError("reports: malformed aggregate response; previous counts preserved")
    for row in rows:
        try:
            valid = (isinstance(row, dict) and row.get("hazard") in {"water", "air", "heat", "flood", "fire"}
                     and isinstance(row.get("place_id"), str) and re.fullmatch(r"[a-z0-9-]{2,60}", row["place_id"])
                     and isinstance(row.get("kind"), str) and re.fullmatch(rf"{row['hazard']}_[a-z]+", row["kind"])
                     and type(row.get("n")) is int and 0 < row["n"] <= 2**53 - 1
                     and isinstance(row.get("day"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["day"])
                     and date.fromisoformat(row["day"]) <= fetched_at.tz_convert("America/Los_Angeles").date())
        except (ValueError, TypeError):
            valid = False
        if not valid:
            raise RuntimeError("reports: malformed aggregate response; previous counts preserved")
    df = pd.DataFrame(rows, columns=["place_id", "hazard", "kind", "day", "n"])
    # This is a replacement window, not an append-only feed. A withdrawn/moderated option
    # disappears from the RPC; retaining absent rows would keep it in the Track record.
    path = PROCESSED / "community_reports.parquet"
    cutoff = (fetched_at - pd.Timedelta(days=days)).tz_convert("America/Los_Angeles").date()
    if path.exists():
        previous = pd.read_parquet(path)
        previous = previous[pd.to_datetime(previous.day).dt.date < cutoff]
        if len(previous):
            df = pd.concat([previous, df], ignore_index=True)
    if len(df):
        df = df.drop_duplicates(["place_id", "hazard", "kind", "day"], keep="last").sort_values(
            ["place_id", "hazard", "kind", "day"]).reset_index(drop=True)
    df = df.astype({"place_id": "str", "hazard": "str", "kind": "str", "day": "str", "n": "int64"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_output(path) as temporary:
        df.to_parquet(temporary, index=False)
    return df
