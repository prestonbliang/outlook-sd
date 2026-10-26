"""Outlook SD API — serves precomputed forecasts written by the hourly pipeline (never trains or calls sources)."""
import json
import math
import sqlite3
from contextlib import closing
from copy import deepcopy
from functools import lru_cache
from datetime import timedelta
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from api.quality import quality
from api.values import coordinates, finite_number
from pipeline.constants import SOURCE_STALE_HOURS as STALE_HOURS
from pipeline.security import official_link, redact
from pipeline.sources.apcd import PAGE as APCD_PAGE, SOUTH_BAY

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "models" / "artifacts"
PROCESSED = ROOT / "data" / "processed"
DB = ROOT / "data" / "outlook.db"
TZ = "America/Los_Angeles"
TILES = ["water", "air", "heat", "flood", "fire"]
PLACES = json.loads((ROOT / "api" / "places.json").read_text())
VERDICTS = json.loads((ROOT / "api" / "verdicts.json").read_text())
ACTIONS = json.loads((ROOT / "api" / "actions.json").read_text())
MLLW = 3.79  # NOAA 9410170: MLLW on station datum (ft); public tide tables use feet above MLLW
WATER_RADIUS_KM = 3.0
SOURCES = {
    "water": ["IBWC gauge 11-0133.00", "State Water Board Beach Watch", "CDIP buoy 191", "Open-Meteo"],
    "heat": ["City of San Diego Fire-Rescue calls", "Open-Meteo", "CalHeatScore (CalEPA/OEHHA)"],
    "flood": ["NOAA tide gauge 9410170", "CDIP buoy 191", "Open-Meteo"],
    "air": ["AirNow (EPA)"],
    "fire": ["CAL FIRE incidents", "NASA FIRMS", "NWS San Diego"],
}
STATUS_KEYS = {"water": ["ibwc", "cdip", "openmeteo"], "heat": ["openmeteo", "sd_fire_ems"],
               "flood": ["noaa_tides", "cdip", "openmeteo"], "air": ["airnow", "openmeteo"], "fire": ["openmeteo"]}
OFFICIAL = {"water": "https://www.sdbeachinfo.com/", "heat": "https://calheatscore.calepa.ca.gov/",
            "flood": "https://tidesandcurrents.noaa.gov/stationhome.html?id=9410170",
            "air": "https://www.airnow.gov/?city=San%20Diego&state=CA&country=USA",
            "fire": "https://www.fire.ca.gov/incidents"}
AQI_CATS = [(50, "good"), (100, "moderate"), (150, "usg"), (200, "unhealthy"), (300, "very_unhealthy"),
            (10_000, "hazardous")]

app = FastAPI(title="Outlook SD", description="3-day neighborhood hazard outlook for San Diego County")


# ------------------------------------------------------------------ data access
def query(sql, params=()):
    # A fresh checkout can serve an honest empty state before the first live run.
    from pipeline.db import SCHEMA
    exists = DB.exists()
    with closing(sqlite3.connect(f"file:{DB}?mode=ro" if exists else ":memory:", uri=True)) as con:
        if not exists:
            con.executescript(SCHEMA)
        return pd.read_sql(sql, con, params=params)


def latest(tile):
    return query("SELECT * FROM forecasts WHERE tile=? AND run_ts=(SELECT MAX(run_ts) FROM forecasts WHERE tile=?) "
                 "AND target_date >= ? ORDER BY target_date", (tile, tile, str(pd.Timestamp.now(tz=TZ).date())))


def artifact(tile, name):
    p = ART / tile / name
    return deepcopy(cached_json(str(p), p.stat().st_mtime_ns)) if p.exists() else None


@lru_cache(maxsize=64)
def cached_json(path, modified):
    """Cache only unchanged artifact files; callers receive independent objects."""
    return json.loads(Path(path).read_text())


def read_parquet(name):
    p = PROCESSED / f"{name}.parquet"
    if not p.exists():
        return None
    # Reuse unchanged inputs during export; callers cannot mutate the cached frame.
    return cached_parquet(str(p), p.stat().st_mtime_ns).copy(deep=True)


@lru_cache(maxsize=12)
def cached_parquet(path, modified):
    return pd.read_parquet(path)


def haversine_km(lat1, lon1, lat2, lon2):
    r = math.pi / 180
    a = (math.sin((lat2 - lat1) * r / 2) ** 2
         + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin((lon2 - lon1) * r / 2) ** 2)
    return 12742 * math.asin(math.sqrt(min(1, max(0, a))))


def nearest_place(lat, lon):
    return min(PLACES, key=lambda p: haversine_km(lat, lon, p["lat"], p["lon"]))


def place_by_id(place_id):
    p = next((p for p in PLACES if p["id"] == place_id), None)
    if not p:
        raise HTTPException(404, f"unknown place_id {place_id}")
    return p


def source_status():
    s = query("SELECT * FROM source_status")
    s = s.astype(object).where(s.notna(), None)
    now = pd.Timestamp.now(tz="UTC")
    out = {k: {"last_success": None, "newest_data": None, "error": "No successful fetch yet",
               "age_hours": None, "stale": True, "reference_at": None,
               "max_age_hours": STALE_HOURS.get(k, 24)} for k in [*STALE_HOURS, "reports"]}
    for r in s.itertuples():
        newest = pd.to_datetime(r.newest_data, utc=True, errors="coerce") if r.newest_data else pd.NaT
        if r.source == "calheatscore" and r.newest_data:
            issued = pd.to_datetime(r.newest_data, errors="coerce")
            if pd.notna(issued) and issued.tzinfo is None:
                # The provider's issue date and heat_tile's run timestamp use Pacific midnight.
                newest = issued.tz_localize(TZ).tz_convert("UTC")
        ref = newest if pd.notna(newest) and r.source not in {"nws", "calfire", "calfire_year", "firms", "reports"} else \
            pd.to_datetime(r.last_success, utc=True, errors="coerce")
        age = (now - ref).total_seconds() / 3600 if pd.notna(ref) else None
        out[r.source] = {"last_success": r.last_success, "newest_data": r.newest_data, "error": redact(r.error) if r.error else None,
                         "age_hours": None if age is None else round(age, 1),
                         "reference_at": ref.isoformat() if pd.notna(ref) else None,
                         "max_age_hours": STALE_HOURS.get(r.source, 24),
                         "stale": age is None or age < -5 / 60 or age > STALE_HOURS.get(r.source, 24)}
    return out


SOURCE_NAMES = {"ibwc": "IBWC border flow", "noaa_tides": "NOAA tide gauge", "cdip": "CDIP wave buoy",
                "openmeteo": "Open-Meteo weather", "sd_fire_ems": "City Fire-Rescue calls (published with a lag)",
                "calheatscore": "CalHeatScore", "airnow": "AirNow", "firms": "NASA FIRMS", "nws": "NWS alerts",
                "calfire": "CAL FIRE incidents", "beachwatch": "Beach Watch samples",
                "apcd": "APCD odor complaints", "cool_zones": "County Cool Zones"}


def stale_inputs(tile, status):
    return [SOURCE_NAMES[k] for k in STATUS_KEYS[tile] if status.get(k, {"stale": True})["stale"]]


def source_check(key, status):
    return {"name": SOURCE_NAMES[key], "reference_at": status.get(key, {}).get("reference_at"),
            "max_age_hours": STALE_HOURS[key]}


def source_checks(tile, status):
    keys = ["calheatscore"] if tile.get("model") == "calheatscore" else STATUS_KEYS[tile["tile"]]
    return [source_check(k, status) for k in keys]


# ------------------------------------------------------------------ tiles
def verdict(tile, level):
    return VERDICTS[tile].get(level or "none", VERDICTS[tile]["none"])


# context that does not change day to day: shown under "Why" on the detail page, not in the one-line reason
STATIC_FEATURES = {"station", "dist_mouth_km", "zip_code", "month", "lead_k", "lead_h", "doy_sin", "doy_cos", "level_365d"}


def reason(level, factors):
    """One line from the top model factors, only when the level is above Low."""
    if level in (None, "low", "good") or not factors:
        return None
    parts = [f"{f['label']}: {f['value']}" for f in factors
             if f["direction"] == "up" and f["value"] and f.get("feature") not in STATIC_FEATURES][:2]
    return "; ".join(parts) or None


def days_from(df, tile, transform=lambda v: v):
    return [{"date": r.target_date, "level": r.level, "value": None if pd.isna(r.value) else transform(r.value),
             "verdict": verdict(tile, r.level)} for r in df.itertuples()]


def empty_tile(tile, why, status):
    return {"tile": tile, "days": [], "reason": why, "factors": [], "official_advisory": {"active": None,
            "url": OFFICIAL[tile]}, "sources": SOURCES[tile], "stale_inputs": stale_inputs(tile, status),
            "verdict": VERDICTS[tile]["unavailable"], "status": "unavailable"}


def water_stations():
    st = artifact("water", "stations.json") or []
    return {str(s["station"]): s for s in st}


def nearest_station(place, fc):
    st = water_stations()
    cands = [(haversine_km(place["lat"], place["lon"], st[u]["lat"], st[u]["lon"]), u) for u in fc.unit_id.unique()
             if u in st]
    cands = [c for c in cands if c[0] <= WATER_RADIUS_KM]
    return (min(cands)[1], st) if cands else (None, st)


def water_tile(place, status):
    fc = latest("water")
    if fc.empty:
        return empty_tile("water", "No water forecast available. Check the official beach status before entering the water.", status)
    sid, st = nearest_station(place, fc) if len(fc) else (None, {})
    if not sid:
        t = empty_tile("water", f"No monitored beach within {WATER_RADIUS_KM:.0f} km of {place['name']}.", status)
        t["verdict"] = verdict("water", None)
        return t
    d = fc[fc.unit_id == sid]
    f0 = json.loads(d.iloc[0].factors_json)
    tile = {"tile": "water", "unit": {"id": sid, "name": st[sid]["beach"], "code": st[sid]["name"]},
            "days": days_from(d, "water", lambda v: round(v, 2)), "factors": f0,
            "official_advisory": {"active": None, "url": OFFICIAL["water"]},
            "sources": SOURCES["water"], "stale_inputs": stale_inputs("water", status), "run_ts": d.iloc[0].run_ts}
    tile["reason"] = reason(d.iloc[0].level, f0)
    return tile


def chs_level(v):
    return {0: "low", 1: "low", 2: "moderate", 3: "high", 4: "very_high"}.get(int(v)) if pd.notna(v) else None


def heat_tile(place, status):
    fc = latest("heat")
    d = fc[fc.unit_id == place["zip"]]
    if len(d):
        f0 = json.loads(d.iloc[0].factors_json)
        extra = [json.loads(x) for x in d.extra_json]
        days = days_from(d, "heat", lambda v: round(v, 1))
        for day, e in zip(days, extra):
            day.update({"expected_calls": e["expected_calls"], "normal_calls": e["normal_calls"],
                        "excess_per_10k": e["excess_per_10k"], "high_f": e["tmax_f"]})
        return {"tile": "heat", "unit": {"id": place["zip"], "name": f"ZIP {place['zip']}"}, "days": days,
                "factors": f0, "reason": reason(d.iloc[0].level, f0), "model": "outlook",
                "official_advisory": {"active": None, "url": OFFICIAL["heat"]}, "sources": SOURCES["heat"],
                "stale_inputs": stale_inputs("heat", status), "run_ts": d.iloc[0].run_ts}
    chs = read_parquet("calheatscore_log")
    if chs is None:
        return empty_tile("heat", "No heat data for this ZIP.", status)
    c = chs[(chs.zip == place["zip"]) & (chs.target_date.astype(str) >= str(pd.Timestamp.now(tz=TZ).date()))]
    c = c[c.issued == c.issued.max()].sort_values("lead_days").head(4)
    if c.empty:
        return empty_tile("heat", "No heat data for this ZIP.", status)
    days = [{"date": str(r.target_date), "level": chs_level(r.chs), "value": None if pd.isna(r.chs) else int(r.chs),
             "verdict": verdict("heat", chs_level(r.chs))} for r in c.itertuples()]
    return {"tile": "heat", "unit": {"id": place["zip"], "name": f"ZIP {place['zip']}"}, "days": days, "factors": [],
            "run_ts": pd.Timestamp(c.issued.max()).tz_localize(TZ).isoformat(),
            "reason": "Showing the state CalHeatScore because a local model forecast is unavailable.",
            "model": "calheatscore", "official_advisory": {"active": None, "url": OFFICIAL["heat"]},
            "sources": ["CalHeatScore (CalEPA/OEHHA)"],
            "stale_inputs": [SOURCE_NAMES[k] for k in ["calheatscore"] if status.get(k, {"stale": True})["stale"]]}


def nws_alerts(events):
    a = read_parquet("nws_alerts_live")
    if a is None or a.empty:
        return []
    if "expires" in a:
        a = a[pd.to_datetime(a.expires, utc=True, errors="coerce") > pd.Timestamp.now(tz="UTC")]
    return a[a.event.isin(events)].to_dict("records")


def alert_status(alerts, status):
    fresh = not status.get("nws", {"stale": True})["stale"]
    expiry = alerts[0].get("expires") if alerts else None
    return {"active": bool(alerts) if fresh else None,
            "headline": alerts[0]["headline"] if alerts else None,
            "check": source_check("nws", status),
            "expires_at": str(expiry) if expiry is not None and pd.notna(expiry) else None,
            "url": "https://www.weather.gov/sgx/"}


def flood_tile(place, status):
    if not place.get("coastal"):
        t = empty_tile("flood", f"{place['name']} is inland, away from the ocean and bay shore.", status)
        t["status"] = "not_applicable"
        t["verdict"] = verdict("flood", None)
        return t
    alerts = nws_alerts(["Coastal Flood Warning", "Coastal Flood Advisory", "Coastal Flood Statement",
                         "High Surf Advisory", "High Surf Warning"])
    advisory = alert_status(alerts, status)
    d = latest("flood")
    if d.empty:
        t = empty_tile("flood", "No flood forecast available.", status)
        t["official_advisory"] = advisory
        return t
    f0 = json.loads(d.iloc[0].factors_json)
    days = days_from(d, "flood", lambda v: round(v - MLLW, 2))
    for day, e in zip(days, (json.loads(x) for x in d.extra_json)):
        day.update({"high_end": round(e["high_end_ft"] - MLLW, 2), "peak_time": e["peak_time"],
                    "tide_only": round(e["tide_only_ft"] - MLLW, 2)})
    return {"tile": "flood", "unit": {"id": "9410170", "name": "San Diego Bay tide gauge"}, "days": days,
            "units": "ft above MLLW (tide-table feet)", "factors": f0, "reason": reason(d.iloc[0].level, f0),
            "official_advisory": advisory,
            "sources": SOURCES["flood"], "stale_inputs": stale_inputs("flood", status), "run_ts": d.iloc[0].run_ts}


def aqi_category(aqi):
    return next(c for lim, c in AQI_CATS if aqi <= lim)


AIR_RADIUS_KM = 30
AQI_ORDER = ["good", "moderate", "usg", "unhealthy", "very_unhealthy", "hazardous"]


def air_forecast(place):
    """Nearest monitor (≤30 km) per pollutant; each day shows the worse of PM2.5 and ozone."""
    fc = latest("air")
    if fc.empty:
        return None
    ex = pd.DataFrame([json.loads(x) for x in fc.extra_json], index=fc.index)
    fc = fc.join(ex[["parameter", "site_name", "lat", "lon", "high_end_aqi"]])
    fc["km"] = [haversine_km(place["lat"], place["lon"], a, b) for a, b in zip(fc.lat, fc.lon)]
    fc = fc[fc.km <= AIR_RADIUS_KM]
    if fc.empty:
        return None
    best = fc.sort_values("km").groupby("parameter").unit_id.first()
    d = fc[fc.unit_id.isin(best.values)].copy()
    d["rank"] = d.level.map(AQI_ORDER.index)
    worst = d.sort_values(["target_date", "rank", "value"]).groupby("target_date").tail(1).sort_values("target_date")
    return worst


def air_tile(place, status):
    obs = read_parquet("airnow_obs")
    w = air_forecast(place)
    if w is not None:
        days = [{"date": r.target_date, "level": r.level, "value": r.value, "verdict": verdict("air", r.level),
                 "pollutant": "PM2.5" if r.parameter == "pm25" else "Ozone", "site": r.site_name,
                 "high_end": r.high_end_aqi} for r in w.itertuples()]
        f0 = json.loads(w.iloc[0].factors_json)
        return {"tile": "air", "unit": {"id": w.iloc[0].unit_id, "name": f"AirNow monitor: {w.iloc[0].site_name}"},
                "days": days, "units": "AQI", "factors": f0, "reason": reason(w.iloc[0].level, f0),
                "official_advisory": {"active": None, "url": OFFICIAL["air"]}, "sources": SOURCES["air"] + ["EPA AirData (training)", "Open-Meteo"],
                "stale_inputs": stale_inputs("air", status), "run_ts": w.iloc[0].run_ts}
    t = empty_tile("air", "Forecast not released yet. See AirNow for current air quality.", status)
    if obs is None or obs.empty:
        return t
    o = obs[obs.ts_utc == obs.ts_utc.max()].copy()
    o["AQI"] = pd.to_numeric(o.AQI, errors="coerce")
    o["km"] = [haversine_km(place["lat"], place["lon"], *point) if (point := coordinates(a, b)) else float("inf")
               for a, b in zip(o.Latitude, o.Longitude)]
    o = o[o.AQI.ge(0) & o.AQI.le(10000) & (o.km <= AIR_RADIUS_KM)].sort_values("km")
    if o.empty:
        return t
    worst = o[o.SiteName == o.iloc[0].SiteName].sort_values("AQI").iloc[-1]
    level = aqi_category(worst.AQI)
    t.update({"current": {"aqi": int(worst.AQI), "parameter": worst.Parameter, "site": worst.SiteName,
                          "time": str(worst.ts_utc), "level": level, "verdict": verdict("air", level)},
              "reason": f"No forecast available. Last recorded AQI {int(worst.AQI)} ({worst.Parameter}) at {worst.SiteName}.",
              "status": "live_only"})
    return t


def fire_tile(place, status):
    fires = read_parquet("calfire_active")
    near = []
    if fires is not None and len(fires):
        for r in fires.itertuples():
            point = coordinates(r.Latitude, r.Longitude)
            if point is None:
                continue
            km = haversine_km(place["lat"], place["lon"], *point)
            if km <= 50:
                near.append({"name": r.Name, "acres": finite_number(r.AcresBurned), "contained_pct": finite_number(r.PercentContained),
                             "km": round(km, 1), "url": official_link(r.Url, OFFICIAL["fire"])})
    red = nws_alerts(["Red Flag Warning", "Fire Weather Watch"])
    advisory = alert_status(red, status)
    available = fires is not None and not status.get("calfire", {"stale": True})["stale"]
    live = {"active_fires": near, "active_fires_available": available,
            "red_flag": [a["headline"] for a in red] if advisory["active"] else []}
    note = (("NWS: " + red[0]["headline"] + ". ") if advisory["active"] else "") + \
           ("Active-fire data is unavailable or not current. Check CAL FIRE." if not available else
            f"{len(near)} active fire(s) within 50 km." if near else "No active CAL FIRE incidents within 50 km.")
    fc = latest("fire")
    d = fc[fc.unit_id == place["id"]] if len(fc) else fc
    if not len(d):
        t = empty_tile("fire", "No fire-start forecast available. " + note, status)
        t.update({**live, "status": "live_only", "official_advisory": advisory})
        return t
    f0 = json.loads(d.iloc[0].factors_json)
    county = fc[fc.unit_id == "county"]
    days = days_from(d, "fire", lambda v: round(v * 100, 3))  # percent chance for the riskiest nearby 2 km cell
    for day in days:
        c = county[county.target_date == day["date"]]
        day["county_expected_fires"] = round(float(c.value.iloc[0]), 2) if len(c) else None
    return {"tile": "fire", "unit": {"id": place["id"], "name": f"Riskiest 2 km area within 5 km of {place['name']}"},
            "days": days, "factors": f0, "reason": reason(d.iloc[0].level, f0) or (note if near or red else None),
            "official_advisory": advisory,
            "sources": SOURCES["fire"], "stale_inputs": stale_inputs("fire", status), "run_ts": d.iloc[0].run_ts, **live}


BUILDERS = {"water": water_tile, "air": air_tile, "heat": heat_tile, "flood": flood_tile, "fire": fire_tile}


def odor_reports(place, days=30):
    """South Bay only: APCD odor complaints over the last 30 days of the log (a record, not a forecast)."""
    if place["zip"] not in SOUTH_BAY:
        return None
    c = read_parquet("odor_complaints")
    if c is None or c.empty:
        return None
    c = c.assign(date=pd.to_datetime(c.date))
    through = c.date.max()
    recent = c[c.zip.isin(SOUTH_BAY) & (c.date > through - pd.Timedelta(days=days))]
    here = recent[recent.zip == place["zip"]]
    return {"through": str(through.date()), "days": days, "south_bay": int(len(recent)), "here": int(len(here)),
            "report_days": int(recent.date.nunique()),
            "last_here": str(here.date.max().date()) if len(here) else None, "url": APCD_PAGE}


def cool_zones_near(place, n=3):
    z = read_parquet("cool_zones")
    if z is None or z.empty:
        return []
    z = z.assign(km=[haversine_km(place["lat"], place["lon"], a, b) for a, b in zip(z.lat, z.lon)]).nsmallest(n, "km")
    text = lambda v: v.strip() if isinstance(v, str) and v.strip() else None
    return [{"name": r.name, "address": f"{r.address}, {r.city}", "km": round(r.km, 1), "hours": text(r.hours),
             "phone": text(r.phone), "pets": text(r.pets)} for r in z.itertuples()]


def outlook_for(place):
    status = source_status()
    tiles = [BUILDERS[t](place, status) for t in TILES]
    for tile in tiles:
        tile["source_checks"] = source_checks(tile, status)
        tile["quality"] = quality(tile)
    runs = [t.get("run_ts") for t in tiles if t.get("run_ts")]
    return {"place": {"id": place["id"], "name": place["name"], "zip": place["zip"], "coastal": place["coastal"]},
            "updated_at": max(runs) if runs else None, "forecast_date": str(pd.Timestamp.now(tz=TZ).date()), "tiles": tiles,
            "odor": odor_reports(place), "cool_zones": cool_zones_near(place)}


# ------------------------------------------------------------------ endpoints
@app.get("/places")
def places(q: str = ""):
    q = q.lower().strip()
    return [p for p in PLACES if not q or q in p["name"].lower() or q in p["zip"]]


@app.get("/outlook")
def outlook(lat: float = Query(..., ge=32.0, le=34.0), lon: float = Query(..., ge=-118.5, le=-115.5)):
    return outlook_for(nearest_place(lat, lon))


@app.get("/outlook/{place_id}")
def outlook_place(place_id: str):
    return outlook_for(place_by_id(place_id))


def series_flood():
    t = read_parquet("tides_9410170")
    if t is None:
        return None
    t = t[t.observed_ft.notna()].sort_values("ts_utc").tail(24 * 7)
    f = read_parquet("flood_forecast_hourly")
    thr = artifact("flood", "thresholds.json")
    return {"units": "ft above MLLW", "threshold": {"value": round(thr["minor"] - MLLW, 2), "label": "Minor flooding"},
            "observed": [{"t": str(r.ts_utc), "v": round(r.observed_ft - MLLW, 2)} for r in t.itertuples()],
            "forecast": [] if f is None else [{"t": str(r.target), "v": round(r.lvl50 - MLLW, 2),
                                               "hi": round(r.lvl90 - MLLW, 2)} for r in f.itertuples()]}


def series_heat(place):
    w = read_parquet("weather_daily_live")
    thr = artifact("heat", "thresholds.json")
    pid = place.get("point_id")
    if w is None or pid is None:
        return None
    w = w[w.point_id == pid].sort_values("date")
    today = pd.Timestamp.now(tz=TZ).normalize().tz_localize(None)
    f = lambda c: round(c * 9 / 5 + 32)
    hot = thr["hot_tmax_p95_c"].get(pid)
    return {"units": "°F, daily high", "observed_label": "Recent weather estimates", "threshold": None if hot is None else {"value": f(hot), "label": "Hot for this area"},
            "observed": [{"t": str(r.date.date()), "v": f(r.tmax)} for r in w[(w.date < today) & (w.date >= today - pd.Timedelta(days=7))].itertuples()],
            "forecast": [{"t": str(r.date.date()), "v": f(r.tmax)} for r in w[(w.date >= today) & (w.date < today + pd.Timedelta(days=4))].itertuples()]}


def series_water(unit_id):
    today = pd.Timestamp.now(tz=TZ).date()
    past = query("SELECT f.target_date, f.value FROM forecasts f WHERE f.tile='water' AND f.unit_id=? AND f.lead_days=0 "
                 "AND f.target_date >= ? AND f.target_date < ? "
                 "AND f.run_ts = (SELECT MAX(g.run_ts) FROM forecasts g WHERE g.tile='water' AND g.unit_id=f.unit_id "
                 "AND g.target_date=f.target_date AND g.lead_days=0) ORDER BY f.target_date",
                 (unit_id, (today - timedelta(days=7)).isoformat(), today.isoformat()))
    fc = latest("water")
    fc = fc[fc.unit_id == unit_id]
    return {"units": "chance bacteria exceed the state standard", "threshold": {"value": 0.5, "label": "Don't swim"},
            "observed_label": "Past forecasts (this site's log)",
            "observed": [{"t": r.target_date, "v": round(r.value, 2)} for r in past.itertuples()],
            "forecast": [{"t": r.target_date, "v": round(r.value, 2)} for r in fc.itertuples()]}


def window(days):
    """'Don't swim through Sunday': last consecutive day (from today) sharing today's verdict."""
    if not days:
        return None
    v, last = days[0]["verdict"], days[0]["date"]
    for d in days[1:]:
        if d["verdict"] != v or pd.Timestamp(d["date"]) - pd.Timestamp(last) != pd.Timedelta(days=1):
            break
        last = d["date"]
    return {"verdict": v, "through": last}


@app.get("/hazard/{tile}")
def hazard(tile: str, place_id: str):
    if tile not in TILES:
        raise HTTPException(404, f"unknown tile {tile}")
    place = place_by_id(place_id)
    status = source_status()
    t = BUILDERS[tile](place, status)
    t["source_checks"] = source_checks(t, status)
    t["quality"] = quality(t)
    level = t["days"][0]["level"] if t.get("days") else None
    series = None
    if tile == "flood" and t.get("days"):
        series = series_flood()
    elif tile == "heat" and t.get("model") == "outlook":
        series = series_heat(place)
    elif tile == "water" and t.get("unit"):
        series = series_water(t["unit"]["id"])
    return {"place": {"id": place["id"], "name": place["name"], "zip": place["zip"], "coastal": place["coastal"]}, **t,
            "window": window(t.get("days", [])), "series": series,
            "what_to_do": ACTIONS[tile].get(level or "none", ACTIONS[tile]["none"]),
            "what_to_do_by_date": {d["date"]: ACTIONS[tile].get(d.get("level") or "none", ACTIONS[tile]["none"]) for d in t.get("days", [])},
            "metrics": track_summary(tile), "cool_zones": cool_zones_near(place) if tile in ("heat", "air") else []}


@app.get("/map/dates")
def map_dates():
    today = pd.Timestamp.now(tz=TZ).date()
    return {"dates": [(today + timedelta(days=k)).isoformat() for k in range(4)]}


@app.get("/map/{tile}")
def map_layer(tile: str, date: str | None = None):
    if tile not in TILES:
        raise HTTPException(404, f"unknown tile {tile}")
    today = str(pd.Timestamp.now(tz=TZ).date())
    date = date or today
    if date not in map_dates()["dates"]:
        raise HTTPException(422, "Map date must be today or one of the next three days (Pacific time)")
    feats = []
    status = source_status()
    context_notice = None
    fc = latest(tile)
    fc = fc[fc.target_date == date]
    mode = "forecast"
    observed_at = None
    if tile == "water":
        st = water_stations()
        for r in fc.itertuples():
            s = st.get(r.unit_id)
            if s:
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
                              "properties": {"id": r.unit_id, "name": s["beach"], "value": round(r.value, 2),
                                             "level": r.level, "label": verdict("water", r.level)}})
    elif tile in ("heat", "flood"):
        path = PROCESSED / f"map_{tile}.geojson"
        outlines = json.loads(path.read_text())["features"] if path.exists() else []
        chs = read_parquet("calheatscore_log") if tile == "heat" else None
        if chs is not None and not chs.empty:
            chs = chs[(chs.issued == chs.issued.max()) & (chs.target_date.astype(str) == date)]
        for f in outlines:
            p = f["properties"]
            # Geometry may be cached; ratings must always come from the selected date.
            for key in ("value", "level", "chs", "peak_ft_mllw", "source", "label"):
                p.pop(key, None)
            rows = fc[fc.unit_id == p.get("zip")] if tile == "heat" else fc
            if len(rows):
                r = rows.iloc[0]
                p.update(level=r.level, source="outlook", label=verdict(tile, r.level))
                p["value" if tile == "heat" else "peak_ft_mllw"] = round(float(r.value) - (MLLW if tile == "flood" else 0), 2)
            elif tile == "heat" and chs is not None:
                c = chs[chs.zip == p.get("zip")]
                if len(c) and pd.notna(c.iloc[0].chs):
                    p.update(chs=int(c.iloc[0].chs), source="calheatscore", level=chs_level(c.iloc[0].chs))
                    p["label"] = verdict("heat", p["level"])
            feats.append(f)
    elif tile == "fire":
        cells = PROCESSED / f"map_fire_cells-{date}.geojson"
        if cells.exists():
            feats += json.loads(cells.read_text())["features"]
        current_incidents = not status.get("calfire", {"stale": True})["stale"]
        fires = read_parquet("calfire_active") if date == today and current_incidents else None
        if date == today and not current_incidents:
            context_notice = "Current active-fire records are unavailable. Check CAL FIRE; older incident markers are hidden."
        for r in ([] if fires is None else fires.itertuples()):
            point = coordinates(r.Latitude, r.Longitude)
            if point is None:
                continue
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [point[1], point[0]]},
                          "properties": {"name": r.Name, "acres": finite_number(r.AcresBurned), "contained_pct": finite_number(r.PercentContained),
                                         "active_fire": True}})
    elif tile == "air":
        # The worse pollutant per monitor, using the same forecast as the detail page.
        candidates = {}
        for r in fc.itertuples():
            p = json.loads(r.extra_json)
            if p["site"] not in candidates or r.value > candidates[p["site"]][0]:
                candidates[p["site"]] = (r.value, r.level, p)
        for value, level, p in candidates.values():
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
                          "properties": {"name": p["site_name"], "aqi": value, "parameter": p["parameter"],
                                         "level": level, "label": verdict("air", level)}})
        obs = read_parquet("airnow_obs") if date == today and not feats else None
        if obs is not None and len(obs):
            mode = "observation"
            observed_at = str(obs.ts_utc.max())
            o = obs[obs.ts_utc == obs.ts_utc.max()]
            o = o[pd.to_datetime(o.ts_utc, utc=True, errors="coerce").dt.tz_convert(TZ).dt.strftime("%Y-%m-%d") == today]
            o = o.assign(AQI=pd.to_numeric(o.AQI, errors="coerce"))
            o = o[o.AQI.ge(0) & o.AQI.le(10000)]
            o = o.sort_values("AQI").groupby("SiteName").tail(1)
            for r in o.itertuples():
                point = coordinates(r.Latitude, r.Longitude)
                if point is None:
                    continue
                lvl = aqi_category(r.AQI) if r.AQI >= 0 else None
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [point[1], point[0]]},
                              "properties": {"name": r.SiteName, "aqi": int(r.AQI), "parameter": r.Parameter,
                                             "level": lvl, "label": verdict("air", lvl)}})
    checks = source_checks({"tile": tile}, status)
    stale = stale_inputs(tile, status)
    if tile == "heat" and any(f["properties"].get("source") == "calheatscore" for f in feats):
        checks.append(source_check("calheatscore", status))
        if status.get("calheatscore", {"stale": True})["stale"]:
            stale.append(SOURCE_NAMES["calheatscore"])
    return {"type": "FeatureCollection", "features": feats, "date": date, "mode": mode,
            "run_ts": observed_at if fc.empty else fc.run_ts.max(), "stale_inputs": stale,
            "source_checks": checks,
            "incident_check": source_check("calfire", status) if tile == "fire" else None,
            "context_notice": context_notice}


LEVEL_WORDS = {"low": "Low", "moderate": "Moderate", "high": "High", "very_high": "Very high"}
REGION = {"all": "all beaches", "south_bay": "South Bay", "rest": "rest of county"}


def track_summary(tile):
    m = artifact(tile, "metrics.json")
    if not m:
        return None
    if tile == "flood":
        hc = m.get("hindcast")
        src, inputs = (hc, "Scored with the weather forecasts that were actually available at the time (archived runs)") \
            if hc else (m, m["inputs"])
        e, r = src["minor_flood_days"], src["residual_rmse_ft"]
        out = {"headline": f"Called {e['q50']['hits']} of {e['q50']['observed_events']} minor-flood days in the test period "
                           f"({e['q50']['false_alarms']} false alarms).",
               "period": m["period"]["test"], "inputs": inputs,
               "table": [{"metric": "Water-level error, ft (RMSE)", "model": r["q50"]["value"], "model_ci95": r["q50"]["ci95"],
                          "baselines": {"Tide only": r["zero"]["value"], "Yesterday's offset": r["persist"]["value"]}},
                         {"metric": "Minor-flood days caught", "model": e["q50"]["hit_rate"],
                          "baselines": {"Tide only": e["zero"]["hit_rate"], "Yesterday's offset": e["persist"]["hit_rate"]}},
                         {"metric": "False-alarm share", "model": e["q50"]["false_alarm_ratio"],
                          "baselines": {"Tide only": None, "Yesterday's offset": e["persist"]["false_alarm_ratio"]}}],
               "replays": m.get("replays", []), "beats_baseline": m["beats_baseline"]}
        if hc:
            out["note"] = (f"With the weather that actually happened, the error would be {m['residual_rmse_ft']['q50']['value']:.3f} ft "
                           f"and {m['minor_flood_days']['q50']['hits']} of {m['minor_flood_days']['q50']['observed_events']} days caught; "
                           "the gap is the cost of imperfect weather forecasts.")
        return out
    if tile == "water":
        a = m["all"]
        return {"headline": f"Picks out risky beach days better than the beach's last lab result does "
                            f"(ranking score {a['prob']['auc']:.2f} vs {a['last_ratio']['auc']:.2f}; 1 is perfect, 0.5 is a coin flip).",
                "reliability": artifact("water", "reliability.json"),
                "period": " → ".join(m["period"]["test"]), "provisional": m["provisional_split"], "inputs": m["inputs"],
                "table": [{"metric": f"AUC ({REGION[r]})", "model": m[r]["prob"].get("auc"),
                           "baselines": {"Last test result": m[r]["last_ratio"].get("auc"),
                                         "Rain rule (0.1 in)": m[r]["rain_rule"].get("auc")}}
                          for r in ("all", "south_bay", "rest")]
                         + [{"metric": "Recall at 80% precision", "model": a["prob"]["recall_at_80pct_precision"],
                             "baselines": {"Last test result": a["last_ratio"]["recall_at_80pct_precision"]}},
                            {"metric": "Brier score", "model": a["prob"]["brier"], "baselines": {}}],
                "beats_baseline": m["beats_baseline"]}
    if tile == "heat":
        c, h = m["citywide_daily_mae"], m["citywide_hot_days"]
        return {"headline": f"Citywide daily calls within {c['pred']['value']:.0f} calls on average "
                            f"(normal-weather model: {c['normal']['value']:.0f}; last week: {c['last_week']['value']:.0f}). "
                            "It under-calls the worst heat waves.",
                "period": m["period"]["test"], "inputs": m["inputs"],
                "table": [{"metric": "Calls per ZIP per day, error (MAE)", "model": m["zip_day_mae"]["pred"]["value"],
                           "model_ci95": m["zip_day_mae"]["pred"]["ci95"],
                           "baselines": {"Normal weather": m["zip_day_mae"]["normal"]["value"],
                                         "Same day last week": m["zip_day_mae"]["last_week"]["value"]}},
                          {"metric": "Citywide calls per day, error (MAE)", "model": c["pred"]["value"],
                           "baselines": {"Normal weather": c["normal"]["value"], "Same day last week": c["last_week"]["value"]}},
                          {"metric": f"Hot-day excess calls, error ({h['n_days']} days)", "model": h["excess_error"]["pred"],
                           "baselines": {"Same day last week": h["excess_error"]["last_week"]}}],
                "note": f"On hot days the model expected {h['mean_predicted_excess']:.0f} extra calls; "
                        f"{h['mean_observed_excess']:.0f} arrived. It under-calls heat waves.",
                "replays": m.get("replays", []), "beats_baseline": m["beats_baseline"]}
    if tile == "fire":
        sa, fl = m["same_alarm_rate"], m["fires_by_level"]
        return {"headline": f"{m['fires_high_or_above']} of {m['test_fires']} large fires in the test period started in an area we rated High or Very high.",
                "period": m["period"]["test"], "inputs": m["inputs"],
                "table": [{"metric": "Times better than random at ranking fire days (AUC-PR ÷ fire rate)",
                           "model": m["auc_pr"]["model"] / m["base_rate"],
                           "baselines": {"Month only": m["auc_pr"]["climatology"] / m["base_rate"],
                                         "Red Flag days": m["auc_pr"]["red_flag"] / m["base_rate"]}},
                          {"metric": "Ranking skill (AUC-ROC; 0.5 = random)", "model": m["auc_roc"]["model"],
                           "baselines": {"Month only": m["auc_roc"]["climatology"], "Red Flag days": None}},
                          {"metric": f"Fires caught when flagging {sa['share_flagged']:.1%} of area-days", "model": sa["model_caught"],
                           "baselines": {"Red Flag days": sa["red_flag_caught"]}}],
                "note": f"Large fires by our level that day: Low {fl['low']}, Moderate {fl['moderate']}, High {fl['high']}, "
                        f"Very high {fl['very_high']}. Fires are rare: {m['test_fires']} in {m['test_cell_days']:,} area-days, "
                        "so the probabilities are tiny and the Brier score is no better than the month-only average; "
                        "the levels are best read as ranks.",
                "replays": [{"name": r["name"], "note": "; ".join(
                    [f"{f['name']} ({f['date']}): its area was rated {LEVEL_WORDS[f['level']]}, riskier than "
                     f"{f['percentile_that_day']:.0f}% of the county that day" for f in r["fires"]]
                    + [f"county-wide expected large fires peaked at {max(d['expected_fires'] for d in r['days']):.2f} "
                       f"per day vs {r['normal_expected_fires']:.2f} on an average day"])} for r in m["replays"]],
                "beats_baseline": m["beats_baseline"]}
    if tile == "air":
        p, o = m["pm25"], m["ozone"]
        return {"headline": f"Next-day AQI within {p['model']['mae']:.0f} points for PM2.5 and {o['model']['mae']:.0f} for ozone "
                            f"on average (yesterday's value: {p['persistence']['mae']:.0f} and {o['persistence']['mae']:.0f}).",
                "period": p["period"]["test"], "inputs": m["inputs"],
                "table": [{"metric": "PM2.5 AQI error (MAE)", "model": p["mae_ci"]["q50"]["value"], "model_ci95": p["mae_ci"]["q50"]["ci95"],
                           "baselines": {"Yesterday's AQI": p["persistence"]["mae"]}},
                          {"metric": "PM2.5 category correct", "model": p["model"]["category_hit_rate"],
                           "baselines": {"Yesterday's AQI": p["persistence"]["category_hit_rate"]}},
                          {"metric": "Ozone AQI error (MAE)", "model": o["mae_ci"]["q50"]["value"], "model_ci95": o["mae_ci"]["q50"]["ci95"],
                           "baselines": {"Yesterday's AQI": o["persistence"]["mae"]}},
                          {"metric": "Ozone category correct", "model": o["model"]["category_hit_rate"],
                           "baselines": {"Yesterday's AQI": o["persistence"]["category_hit_rate"]}}],
                "note": f"Unhealthy-for-sensitive-groups days: the high-end forecast caught {o['model_high_end']['usg_hits']} of "
                        f"{o['model_high_end']['usg_days']} ozone days ({o['model_high_end']['usg_false_alarms']} false alarms) and "
                        f"{p['model_high_end']['usg_hits']} of {p['model_high_end']['usg_days']} PM2.5 days "
                        f"({p['model_high_end']['usg_false_alarms']} false alarms); yesterday's AQI caught "
                        f"{o['persistence']['usg_hits']} and {p['persistence']['usg_hits']}. Live forecasts start once AirNow is connected.",
                "beats_baseline": m["beats_baseline"]}
    return None


def live_log():
    s = query("SELECT f.tile, COUNT(*) n, SUM(s.hit) hits, MIN(f.target_date) since, SUM(s.observed_value) obs, "
              "SUM(f.value) expected FROM scores s JOIN forecasts f ON f.id = s.forecast_id GROUP BY f.tile")
    num = lambda v: 0 if pd.isna(v) else v  # SUM over only-NULL values (e.g. fire's yes/no hit) is NaN, not 0
    out = {r.tile: {"scored": int(r.n), "hits": int(num(r.hits)), "since": r.since} for r in s.itertuples()}
    for r in s[s.tile == "fire"].itertuples():  # fire is scored county-wide: expected vs observed large fires
        out["fire"].update({"observed_fires": int(num(r.obs)), "expected_fires": round(float(num(r.expected)), 1)})
    return out


PROBLEM_KINDS = {"water_sewage", "water_sign", "air_smoke", "heat_extreme", "flood_street", "flood_overtop", "fire_smoke"}
CLEAR_KINDS = {"water_ok", "air_ok", "heat_ok", "flood_ok", "fire_ok"}
ELEVATED = {"moderate", "high", "very_high", "usg", "unhealthy", "very_unhealthy", "hazardous"}


def community_check():
    """Community reports vs what the app said for that place and day (latest run that day).
    A problem report agrees when the level was Moderate or above; an all-clear agrees when it was Low/Good."""
    rep = read_parquet("community_reports")
    if rep is None or rep.empty:
        return {}
    lv = query("SELECT place_id, hazard, target_date AS day, level FROM place_levels p WHERE run_ts = "
               "(SELECT MAX(run_ts) FROM place_levels q WHERE q.place_id=p.place_id AND q.hazard=p.hazard "
               "AND q.target_date=p.target_date)")
    rep = rep.assign(day=rep.day.astype(str)).merge(lv, on=["place_id", "hazard", "day"], how="left")
    out = {}
    for hz, g in rep.groupby("hazard"):
        # Additional observations (e.g. litter or access to shade) are context, not model outcome labels.
        prob, ok = g[g.kind.isin(PROBLEM_KINDS)], g[g.kind.isin(CLEAR_KINDS)]
        context = g[~g.kind.isin(PROBLEM_KINDS | CLEAR_KINDS)]
        rated_p, rated_o = prob[prob.level.notna()], ok[ok.level.notna()]
        out[hz] = {"problem_reports": int(prob.n.sum()), "all_clear_reports": int(ok.n.sum()),
                   "problem_on_elevated_days": int(rated_p[rated_p.level.isin(ELEVATED)].n.sum()),
                   "problem_rated": int(rated_p.n.sum()),
                   "all_clear_on_low_days": int(rated_o[~rated_o.level.isin(ELEVATED)].n.sum()),
                   "all_clear_rated": int(rated_o.n.sum()), "context_reports": int(context.n.sum()), "since": str(g.day.min())}
    return out


@app.get("/track-record")
def track_record():
    log, comm = live_log(), community_check()
    return {"tiles": {t: {"held_out": track_summary(t), "live": log.get(t), "community": comm.get(t)} for t in TILES},
            "odor": artifact("odor", "metrics.json")}


@app.get("/scenarios")
def scenarios():
    out = artifact("scenarios", "scenarios.json")
    if not out:
        return {"flow": None, "sea_level": None}
    f = read_parquet("ibwc_flow")
    if isinstance(out.get("flow"), dict) and f is not None and len(f):
        week = f[f.ts_utc >= f.ts_utc.max() - pd.Timedelta(days=7)].discharge_m3s.dropna()
        if len(week):
            out["flow"]["recent_mgd"] = round(float(week.mean()) / 0.0438126)
            out["flow"]["recent_through"] = str(f.ts_utc.max())
    return out


@app.get("/health")
def health():
    return {"sources": source_status(), "now": str(pd.Timestamp.now(tz="UTC"))}
