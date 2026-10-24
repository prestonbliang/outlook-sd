"""Community reports from the app (Supabase): daily counts per place, hazard and report type (no raw rows)."""
import os

import pandas as pd
import requests

from ._common import redact, upsert


def fetch_live(days=30):
    url, key = os.environ.get("NEXT_PUBLIC_SUPABASE_URL"), os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if not url or not key:
        raise RuntimeError("Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY)")
    r = requests.post(f"{url}/rest/v1/rpc/report_counts", json={"days": days}, timeout=60,
                      headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    if r.status_code != 200:
        raise RuntimeError(redact(f"reports: HTTP {r.status_code} {r.text[:300]}"))
    df = pd.DataFrame(r.json(), columns=["place_id", "hazard", "kind", "day", "n"])
    return upsert(df, "community_reports", ["place_id", "hazard", "kind", "day"]) if len(df) else df
