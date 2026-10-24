"""Refresh the canonical reporting neighborhood whitelist after make history SOURCES=geo."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "supabase/schema.sql"
text = path.read_text()
start = "insert into public.report_places (id, coastal) values\n"
end = "\non conflict (id) do update set coastal = excluded.coastal;"
before, rest = text.split(start, 1)
_, after = rest.split(end, 1)
places = json.loads((ROOT / "api/places.json").read_text())
if not all(re.fullmatch(r"[a-z0-9-]{2,60}", p["id"]) for p in places):
    raise ValueError("Every place ID must use 2–60 lowercase letters, digits, or hyphens")
values = ",\n".join(f"  ('{p['id']}', {str(p['coastal']).lower()})" for p in places)
path.write_text(before + start + values + end + after)
print(f"Updated {len(places)} neighborhoods in supabase/schema.sql. Reapply that file in Supabase SQL Editor.")
