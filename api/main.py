"""Outlook SD API — serves precomputed forecasts written by the hourly pipeline (never trains or calls sources)."""
import json
import math
import sqlite3
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query

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
STATUS_KEYS = {"water": ["ibwc", "cdip", "openmeteo"], "heat": ["openmeteo", "sd_fire_ems", "calheatscore"],
               "flood": ["noaa_tides", "cdip", "openmeteo"], "air": ["airnow"], "fire": ["calfire", "firms", "nws"]}
STALE_HOURS = {"ibwc": 3, "noaa_tides": 2, "airnow": 3, "cdip": 6, "calheatscore": 26, "beachwatch": 240,
               "sd_fire_ems": 72, "firms": 24, "openmeteo": 3, "nws": 3, "calfire": 24}
OFFICIAL = {"water": "https://www.sdbeachinfo.com/", "heat": "https://calheatscore.calepa.ca.gov/",
            "flood": "https://tidesandcurrents.noaa.gov/stationhome.html?id=9410170",
            "air": "https://www.airnow.gov/?city=San%20Diego&state=CA&country=USA",
            "fire": "https://www.fire.ca.gov/incidents"}
AQI_CATS = [(50, "good"), (100, "moderate"), (150, "usg"), (200, "unhealthy"), (300, "very_unhealthy"),
            (10_000, "hazardous")]

app = FastAPI(title="Outlook SD", description="3-day neighborhood hazard outlook for San Diego County")


# ------------------------------------------------------------------ data access
def query(sql, params=()):
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as con:
        return pd.read_sql(sql, con, params=params)


def latest(tile):
    return query("SELECT * FROM forecasts WHERE tile=? AND run_ts=(SELECT MAX(run_ts) FROM forecasts WHERE tile=?) "
                 "ORDER BY target_date", (tile, tile))


def artifact(tile, name):
    p = ART / tile / name
    return json.loads(p.read_text()) if p.exists() else None


def read_parquet(name):
    p = PROCESSED / f"{name}.parquet"
    return pd.read_parquet(p) if p.exists() else None


def haversine_km(lat1, lon1, lat2, lon2):
    r = math.pi / 180
    a = (math.sin((lat2 - lat1) * r / 2) ** 2
         + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin((lon2 - lon1) * r / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


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
    out = {}
    for r in s.itertuples():
        newest = pd.to_datetime(r.newest_data, utc=True, errors="coerce") if r.newest_data else pd.NaT
        ref = newest if pd.notna(newest) else pd.to_datetime(r.last_success, utc=True, errors="coerce")
        age = (now - ref).total_seconds() / 3600 if pd.notna(ref) else None
        out[r.source] = {"last_success": r.last_success, "newest_data": r.newest_data, "error": r.error,
                         "age_hours": None if age is None else round(age, 1),
                         "stale": age is None or age > STALE_HOURS.get(r.source, 24)}
    return out


SOURCE_NAMES = {"ibwc": "IBWC border flow", "noaa_tides": "NOAA tide gauge", "cdip": "CDIP wave buoy",
                "openmeteo": "Open-Meteo weather", "sd_fire_ems": "City Fire-Rescue calls (published with a lag)",
                "calheatscore": "CalHeatScore", "airnow": "AirNow", "firms": "NASA FIRMS", "nws": "NWS alerts",
                "calfire": "CAL FIRE incidents", "beachwatch": "Beach Watch samples"}


def stale_inputs(tile, status):
    return [SOURCE_NAMES[k] for k in STATUS_KEYS[tile] if status.get(k, {"stale": True})["stale"]]


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
            "verdict": verdict(tile, None), "status": "unavailable"}


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
    sid, st = nearest_station(place, fc) if len(fc) else (None, {})
    if not sid:
        return empty_tile("water", f"No monitored beach within {WATER_RADIUS_KM:.0f} km of {place['name']}.", status)
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
    c = chs[chs.zip == place["zip"]]
    c = c[c.issued == c.issued.max()].sort_values("lead_days").head(4)
    if c.empty:
        return empty_tile("heat", "No heat data for this ZIP.", status)
    days = [{"date": str(r.target_date), "level": chs_level(r.chs), "value": int(r.chs),
             "verdict": verdict("heat", chs_level(r.chs))} for r in c.itertuples()]
    return {"tile": "heat", "unit": {"id": place["zip"], "name": f"ZIP {place['zip']}"}, "days": days, "factors": [],
            "reason": "Outside the City of San Diego Fire-Rescue area: showing the state CalHeatScore.",
            "model": "calheatscore", "official_advisory": {"active": None, "url": OFFICIAL["heat"]},
            "sources": ["CalHeatScore (CalEPA/OEHHA)"],
            "stale_inputs": [SOURCE_NAMES[k] for k in ["calheatscore"] if status.get(k, {"stale": True})["stale"]]}


def nws_alerts(events):
    a = read_parquet("nws_alerts_live")
    if a is None or a.empty:
        return []
    return a[a.event.isin(events)].to_dict("records")


def flood_tile(place, status):
    if not place.get("coastal"):
        t = empty_tile("flood", f"{place['name']} is inland, away from the ocean and bay shore.", status)
        t["status"] = "not_applicable"
        return t
    d = latest("flood")
    if d.empty:
        return empty_tile("flood", "No flood forecast available.", status)
    f0 = json.loads(d.iloc[0].factors_json)
    days = days_from(d, "flood", lambda v: round(v - MLLW, 2))
    for day, e in zip(days, (json.loads(x) for x in d.extra_json)):
        day.update({"high_end": round(e["high_end_ft"] - MLLW, 2), "peak_time": e["peak_time"],
                    "tide_only": round(e["tide_only_ft"] - MLLW, 2)})
    alerts = nws_alerts(["Coastal Flood Warning", "Coastal Flood Advisory", "Coastal Flood Statement",
                         "High Surf Advisory", "High Surf Warning"])
    return {"tile": "flood", "unit": {"id": "9410170", "name": "San Diego Bay tide gauge"}, "days": days,
            "units": "ft above MLLW (tide-table feet)", "factors": f0, "reason": reason(d.iloc[0].level, f0),
            "official_advisory": {"active": bool(alerts), "headline": alerts[0]["headline"] if alerts else None,
                                  "url": OFFICIAL["flood"]},
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
    o["km"] = [haversine_km(place["lat"], place["lon"], a, b) for a, b in zip(o.Latitude, o.Longitude)]
    o = o[o.AQI >= 0].sort_values("km")
    if o.empty:
        return t
    worst = o[o.SiteName == o.iloc[0].SiteName].sort_values("AQI").iloc[-1]
    level = aqi_category(worst.AQI)
    t.update({"current": {"aqi": int(worst.AQI), "parameter": worst.Parameter, "site": worst.SiteName,
                          "time": str(worst.ts_utc), "level": level, "verdict": verdict("air", level)},
              "reason": f"Forecast coming soon. Now: AQI {int(worst.AQI)} ({worst.Parameter}) at {worst.SiteName}.",
              "status": "live_only"})
    return t


def fire_tile(place, status):
    fires = read_parquet("calfire_active")
    near = []
    if fires is not None and len(fires):
        for r in fires.itertuples():
            km = haversine_km(place["lat"], place["lon"], r.Latitude, r.Longitude)
            if km <= 50:
                near.append({"name": r.Name, "acres": r.AcresBurned, "contained_pct": r.PercentContained,
                             "km": round(km, 1), "url": r.Url})
    red = nws_alerts(["Red Flag Warning", "Fire Weather Watch"])
    live = {"active_fires": near, "red_flag": [a["headline"] for a in red]}
    note = ("Red Flag Warning in effect. " if red else "") + \
           (f"{len(near)} active fire(s) within 50 km." if near else "No active CAL FIRE incidents within 50 km.")
    fc = latest("fire")
    d = fc[fc.unit_id == place["id"]] if len(fc) else fc
    if not len(d):
        t = empty_tile("fire", "Fire-start forecast coming soon. " + note, status)
        t.update({**live, "status": "live_only"})
        return t
    f0 = json.loads(d.iloc[0].factors_json)
    county = fc[fc.unit_id == "county"]
    days = days_from(d, "fire", lambda v: round(v * 100, 3))  # percent chance for the riskiest nearby 2 km cell
    for day in days:
        c = county[county.target_date == day["date"]]
        day["county_expected_fires"] = round(float(c.value.iloc[0]), 2) if len(c) else None
    return {"tile": "fire", "unit": {"id": place["id"], "name": f"Riskiest 2 km area within 5 km of {place['name']}"},
            "days": days, "factors": f0, "reason": reason(d.iloc[0].level, f0) or (note if near or red else None),
            "official_advisory": {"active": bool(red), "headline": red[0]["headline"] if red else None, "url": OFFICIAL["fire"]},
            "sources": SOURCES["fire"], "stale_inputs": stale_inputs("fire", status), "run_ts": d.iloc[0].run_ts, **live}


BUILDERS = {"water": water_tile, "air": air_tile, "heat": heat_tile, "flood": flood_tile, "fire": fire_tile}


def outlook_for(place):
    status = source_status()
    tiles = [BUILDERS[t](place, status) for t in TILES]
    runs = [t.get("run_ts") for t in tiles if t.get("run_ts")]
    return {"place": {"id": place["id"], "name": place["name"], "zip": place["zip"]},
            "updated_at": max(runs) if runs else None, "tiles": tiles}


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
    return {"units": "°F, daily high", "threshold": None if hot is None else {"value": f(hot), "label": "Hot for this area"},
            "observed": [{"t": str(r.date.date()), "v": f(r.tmax)} for r in w[(w.date < today) & (w.date >= today - pd.Timedelta(days=7))].itertuples()],
            "forecast": [{"t": str(r.date.date()), "v": f(r.tmax)} for r in w[(w.date >= today) & (w.date < today + pd.Timedelta(days=4))].itertuples()]}


def series_water(unit_id):
    past = query("SELECT f.target_date, f.value FROM forecasts f WHERE f.tile='water' AND f.unit_id=? AND f.lead_days=0 "
                 "AND f.target_date >= date('now','-7 day') AND f.target_date < date('now','localtime') "
                 "AND f.run_ts = (SELECT MAX(g.run_ts) FROM forecasts g WHERE g.tile='water' AND g.unit_id=f.unit_id "
                 "AND g.target_date=f.target_date AND g.lead_days=0) ORDER BY f.target_date", (unit_id,))
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
        if d["verdict"] != v:
            break
        last = d["date"]
    return {"verdict": v, "through": last}


@app.get("/hazard/{tile}")
def hazard(tile: str, place_id: str):
    if tile not in TILES:
        raise HTTPException(404, f"unknown tile {tile}")
    place = place_by_id(place_id)
    t = BUILDERS[tile](place, source_status())
    level = t["days"][0]["level"] if t.get("days") else None
    series = None
    if tile == "flood" and t.get("days"):
        series = series_flood()
    elif tile == "heat" and t.get("model") == "outlook":
        series = series_heat(place)
    elif tile == "water" and t.get("unit"):
        series = series_water(t["unit"]["id"])
    return {"place": {"id": place["id"], "name": place["name"], "zip": place["zip"]}, **t,
            "window": window(t.get("days", [])), "series": series,
            "what_to_do": ACTIONS[tile].get(level or "none", ACTIONS[tile]["none"]),
            "metrics": track_summary(tile)}


@app.get("/map/{tile}")
def map_layer(tile: str, date: str | None = None):
    if tile not in TILES:
        raise HTTPException(404, f"unknown tile {tile}")
    feats = []
    if tile == "water":
        fc, st = latest("water"), water_stations()
        fc = fc[fc.target_date == (date or fc.target_date.min())]
        for r in fc.itertuples():
            s = st.get(r.unit_id)
            if s:
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
                              "properties": {"id": r.unit_id, "name": s["beach"], "value": round(r.value, 2),
                                             "level": r.level, "label": verdict("water", r.level)}})
    elif tile in ("heat", "flood"):
        path = PROCESSED / f"map_{tile}.geojson"
        if path.exists():
            return json.loads(path.read_text())
    elif tile == "fire":
        cells = PROCESSED / "map_fire_cells.geojson"
        if cells.exists():
            feats += json.loads(cells.read_text())["features"]
        fires = read_parquet("calfire_active")
        for r in ([] if fires is None else fires.itertuples()):
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [r.Longitude, r.Latitude]},
                          "properties": {"name": r.Name, "acres": r.AcresBurned, "contained_pct": r.PercentContained,
                                         "active_fire": True}})
    elif tile == "air":
        obs = read_parquet("airnow_obs")
        if obs is not None and len(obs):
            o = obs[obs.ts_utc == obs.ts_utc.max()]
            for r in o.itertuples():
                lvl = aqi_category(r.AQI) if r.AQI >= 0 else None
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [r.Longitude, r.Latitude]},
                              "properties": {"name": r.SiteName, "aqi": int(r.AQI), "parameter": r.Parameter,
                                             "level": lvl, "label": verdict("air", lvl)}})
    return {"type": "FeatureCollection", "features": feats}


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
        return {"headline": f"Ranks unsafe-water days correctly {a['prob']['auc']:.0%} of the time (AUC), "
                            f"vs {a['last_ratio']['auc']:.0%} for the last test result.",
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
                            f"(normal-weather model: {c['normal']['value']:.0f}; last week: {c['last_week']['value']:.0f}).",
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
    out = {r.tile: {"scored": int(r.n), "hits": int(r.hits or 0), "since": r.since} for r in s.itertuples()}
    for r in s[s.tile == "fire"].itertuples():  # fire is scored county-wide: expected vs observed large fires
        out["fire"].update({"observed_fires": int(r.obs or 0), "expected_fires": round(float(r.expected or 0), 1)})
    return out


PROBLEM_KINDS = {"water_sewage", "water_sign", "air_smoke", "heat_extreme", "flood_street", "flood_overtop", "fire_smoke"}
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
        prob, ok = g[g.kind.isin(PROBLEM_KINDS)], g[~g.kind.isin(PROBLEM_KINDS)]
        rated_p, rated_o = prob[prob.level.notna()], ok[ok.level.notna()]
        out[hz] = {"problem_reports": int(prob.n.sum()), "all_clear_reports": int(ok.n.sum()),
                   "problem_on_elevated_days": int(rated_p[rated_p.level.isin(ELEVATED)].n.sum()),
                   "problem_rated": int(rated_p.n.sum()),
                   "all_clear_on_low_days": int(rated_o[~rated_o.level.isin(ELEVATED)].n.sum()),
                   "all_clear_rated": int(rated_o.n.sum()), "since": str(g.day.min())}
    return out


@app.get("/track-record")
def track_record():
    log, comm = live_log(), community_check()
    return {"tiles": {t: {"held_out": track_summary(t), "live": log.get(t), "community": comm.get(t)} for t in TILES}}


@app.get("/health")
def health():
    return {"sources": source_status(), "now": str(pd.Timestamp.now(tz="UTC"))}
