"""Community reports from the app (Supabase): daily counts per place, hazard and report type (no raw rows)."""
import os

import pandas as pd
import requests

from ._common import redact, upsert


def fetch_live(days=30):
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
    df = pd.DataFrame(r.json(), columns=["place_id", "hazard", "kind", "day", "n"])
    return upsert(df, "community_reports", ["place_id", "hazard", "kind", "day"]) if len(df) else df
