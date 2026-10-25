"""Live inference for the trained tiles. Each function returns forecast rows for days 0–3 (local dates):
{unit_id, target_date, lead_days, value, level, factors, extra}. Weather comes from the Open-Meteo forecast."""
import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from models.common import ART
from pipeline.features import air, fire, flood, heat, water
from pipeline.sources import noaa_tides, openmeteo
from pipeline.sources._common import PROCESSED, ROOT

TZ = "America/Los_Angeles"
BORDER_LAT = 32.5343  # U.S.–Mexico border where it meets the Pacific
LABELS = {t: json.loads((ROOT / "pipeline" / "features" / f"{t}_labels.json").read_text())
          for t in ("flood", "heat", "water", "fire", "air")}
C_TO_F = lambda c: c * 9 / 5 + 32
MGD = lambda q: q / 0.0438126  # m³/s → million gallons per day, the unit used in sewage news and policy
# feature → (unit, converter) for the plain-language "why" lines; None = show the label only
UNITS = {
    "flood": {"resid_now": ("ft", None), "resid_mean_24h": ("ft", None), "resid_mean_7d": ("ft", None),
              "tide_pred": ("ft", None), "pressure": ("hPa", None), "pressure_change": ("hPa", None),
              "wind_speed_10m": ("mph", lambda v: v * 2.237), "wind_gusts_10m": ("mph", lambda v: v * 2.237),
              "u10": ("mph", lambda v: v * 2.237), "v10": ("mph", lambda v: v * 2.237), "hs_now": ("ft", lambda v: v * 3.281),
              "tp_now": ("s", None), "sst_anom": ("°F", lambda v: v * 9 / 5)},
    "water": {"q_24h": ("million gal/day", MGD), "q_72h": ("million gal/day", MGD), "q_7d": ("million gal/day", MGD),
              "q_max_7d": ("million gal/day", MGD),
              "rain_24h": ("in", lambda v: v / 25.4), "rain_72h": ("in", lambda v: v / 25.4),
              "rain_fcst": ("in", lambda v: v / 25.4), "hs": ("ft", lambda v: v * 3.281), "tp": ("s", None),
              "dp": ("°", None), "sst": ("°F", C_TO_F), "tide_max": ("ft", None), "dist_mouth_km": ("km", None)},
    "fire": {"tmax": ("°F", C_TO_F), "rh_min": ("%", None), "wind_max": ("mph", lambda v: v * 2.237),
             "wind_mean": ("mph", lambda v: v * 2.237), "offshore_hours": ("hours", None), "days_since_rain": ("days", None),
             "dist_road_km": ("km", None), "fhsz_very_high": ("%", lambda v: v * 100), "fhsz_high": ("%", lambda v: v * 100)},
    "air": {"aqi_prev": ("AQI", None), "aqi_prev_mean7": ("AQI", None), "tmax": ("°F", C_TO_F), "tmin": ("°F", C_TO_F),
            "rh_mean": ("%", None), "wind_mean": ("mph", lambda v: v * 2.237), "wind_max": ("mph", lambda v: v * 2.237),
            "blh_max": ("ft", lambda v: v * 3.281), "precip": ("in", lambda v: v / 25.4), "offshore_hours": ("hours", None)},
    "heat": {"tmax": ("°F", C_TO_F), "tmin": ("°F", C_TO_F), "heat_index_max": ("°F", None), "rh_mean": ("%", None),
             "tmax_lag1": ("°F", C_TO_F), "hot_streak": ("days", None), "level_365d": ("calls/day", None)},
}


def top_factors(tile, model, row, n=3, only=None):
    """TreeSHAP contributions (LightGBM pred_contrib) for one feature row → top-n plain-language factors.
    only: restrict to these features (e.g. Heat explains the weather part, not the calendar)."""
    contrib = model.predict(row, pred_contrib=True)[0][:-1]
    allowed = np.array([only is None or c in only for c in row.columns])
    order = [i for i in np.argsort(-np.abs(contrib)) if allowed[i]][:n]
    out = []
    for i in order:
        f = row.columns[i]
        unit, conv = UNITS.get(tile, {}).get(f, (None, None))
        v = row.iloc[0, i]
        text = ""
        if unit and pd.notna(v):
            v = conv(v) if conv else v
            sep = "" if unit in ("%", "°F", "°") else " "
            text = f"{v:.2f}{sep}{unit}" if abs(v) < 10 else f"{v:.0f}{sep}{unit}"
        out.append({"feature": f, "label": LABELS[tile].get(f, f), "value": text,
                    "direction": "up" if contrib[i] > 0 else "down", "contribution": round(float(contrib[i]), 4)})
    return out


def level_of(value, levels):
    for name, (lo, hi) in levels.items():
        if (lo is None or value >= lo) and (hi is None or value < hi):
            return name
    return None


def local_today(now):
    return now.tz_convert(TZ).normalize().tz_localize(None)


def forecast_hourly(point_ids):
    pts = pd.DataFrame({"point_id": point_ids})
    pts["lat"] = pts.point_id.str.extract(r"g([-\d.]+)_")[0].astype(float)
    pts["lon"] = pts.point_id.str.extract(r"_([-\d.]+)$")[0].astype(float)
    fc = openmeteo.forecast(pts, days=5, past_days=10)
    return {p: g.set_index("ts_utc").sort_index() for p, g in fc.groupby("point_id")}


# ---------------------------------------------------------------- Flood
def now_offset(resid):
    """The model forecasts the change from the current offset, so the offset itself is the first reason."""
    return {"feature": "resid_now", "label": "Ocean running above the tide table now", "value": f"{resid:+.2f} ft",
            "direction": "up" if resid > 0 else "down", "contribution": None}


def predict_flood(now, wx):
    art = ART / "flood"
    m50, m90 = lgb.Booster(model_file=str(art / "model_q50.txt")), lgb.Booster(model_file=str(art / "model_q90.txt"))
    thr = json.loads((art / "thresholds.json").read_text())
    tides = flood.load_tides()
    fut = noaa_tides.predictions(flood.STATION, local_today(now) - pd.Timedelta(days=1), local_today(now) + pd.Timedelta(days=6))
    tides = tides.reindex(tides.index.union(fut.set_index("ts_utc").index))
    tides["predicted_ft"] = tides.predicted_ft.fillna(fut.set_index("ts_utc").ft)
    issue = tides.observed_ft.dropna().index.max()
    weather = flood.add_wind_components(wx[flood.POINT].copy())
    rows = flood.build(pd.DatetimeIndex([issue]), tides, weather, flood.load_waves(), weather.surface_pressure)
    rows["q50"] = rows.resid_now + m50.predict(rows[flood.FEATURES])
    rows["q90"] = rows.resid_now + m90.predict(rows[flood.FEATURES])
    rows["lvl50"], rows["lvl90"] = rows.tide_pred + rows.q50, rows.tide_pred + rows.q90
    rows["local"] = rows.target.dt.tz_convert(TZ)
    today = local_today(now)
    obs_today = tides.observed_ft[tides.index.tz_convert(TZ).normalize().tz_localize(None) == today].max()
    out = []
    for k in range(4):
        day = today + pd.Timedelta(days=k)
        g = rows[rows.local.dt.normalize().dt.tz_localize(None) == day]
        if g.empty:
            continue
        peak = g.loc[g.lvl50.idxmax()]
        value = float(peak.lvl50)
        if k == 0 and pd.notna(obs_today):
            value = max(value, float(obs_today))
        out.append({"unit_id": flood.STATION, "target_date": f"{day:%Y-%m-%d}", "lead_days": k,
                    "value": round(value, 2), "level": level_of(value, thr["levels"]),
                    "factors": [now_offset(peak.resid_now)] + top_factors("flood", m50, g.loc[[peak.name], flood.FEATURES], n=2,
                                                                  only=set(flood.FEATURES) - {"resid_now"}),
                    "extra": {"high_end_ft": round(max(float(g.lvl90.max()), value), 2), "peak_time": peak.local.isoformat(),
                              "tide_only_ft": round(float(peak.tide_pred), 2), "hours_covered": int(len(g)),
                              "issued_obs_time": issue.isoformat(), "observed_so_far_ft": None if k else obs_today}})
    return out, rows


# ---------------------------------------------------------------- Water
def predict_water(now, wx, active_since="2024-01-01"):
    art = ART / "water"
    m = lgb.Booster(model_file=str(art / "model.txt"))
    cal = json.loads((art / "calibration.json").read_text())
    levels = json.loads((art / "thresholds.json").read_text())["levels"]
    lab, st = water.labels()
    recent = lab[lab.date >= active_since].station.unique()
    # stations south of the international border (Playas de Tijuana) stay in training but are not shown
    st = st[st.index.isin(recent) & st.point_id.isin(wx) & (st.lat > BORDER_LAT)]
    today = local_today(now)
    q = pd.DataFrame([(s, today + pd.Timedelta(days=k)) for s in st.index for k in range(4)], columns=["station", "date"])
    q["exceed"], q["ratio"] = np.nan, np.nan
    rain = {p: water.rain_daily(p, source=wx[p]) for p in st.point_id.unique()}
    rows = water.build(q, st, water.flow_daily(), water.waves_daily(),
                       pd.concat([water.tide_daily(), _tide_future(today)]).groupby(level=0).max(), rain)
    rows = rows[rows.lead_k == (rows.date - today).dt.days]  # issue = today for every target day
    rows["station"] = pd.Categorical(rows.station.astype(str),
                                     categories=json.loads((art / "station_categories.json").read_text()))
    raw = m.predict(rows[water.FEATURES])
    rows["prob"] = np.interp(raw, cal["x"], cal["y"])
    out = []
    for i, r in rows.iterrows():
        out.append({"unit_id": str(r.station), "target_date": f"{r.date:%Y-%m-%d}", "lead_days": int(r.lead_k),
                    "value": round(float(r.prob), 3), "level": level_of(r.prob, levels),
                    "factors": top_factors("water", m, rows.loc[[i], water.FEATURES]),
                    "extra": {"station_name": st.loc[str(r.station), "name"], "beach": st.loc[str(r.station), "beach"],
                              "flow_m3s_24h": None if pd.isna(r.q_24h) else round(float(r.q_24h), 2),
                              "flow_missing": bool(pd.isna(r.q_7d))}})
    return out, rows


def _tide_future(today):
    fut = noaa_tides.predictions(flood.STATION, today, today + pd.Timedelta(days=5)).set_index("ts_utc").ft
    return water.daily_local(fut, "max")


# ---------------------------------------------------------------- Heat
def predict_heat(now, wx):
    art = ART / "heat"
    m = lgb.Booster(model_file=str(art / "model.txt"))
    thr = json.loads((art / "thresholds.json").read_text())
    norm = json.loads((art / "normals.json").read_text())
    zips = m.pandas_categorical[0]
    zp = heat.zip_points()
    zp = zp[zp.zip.isin(zips) & zp.point_id.isin(wx)]
    today = local_today(now)
    dates = pd.date_range(today, periods=4)
    w, _ = heat.weather_by_point(zp.point_id.unique(), hot_thr=thr["streak_tmax_p90_c"],
                                 source={p: wx[p] for p in zp.point_id.unique()})
    ems = pd.read_parquet(PROCESSED / "ems_daily_zip.parquet").assign(date=lambda x: pd.to_datetime(x.date))
    lvl = heat.call_level(ems, until=dates.max())
    grid = pd.DataFrame([(d, z) for d in dates for z in zp.zip], columns=["date", "zip"]).merge(zp, on="zip")
    df = heat.calendar(grid.merge(w, on=["date", "point_id"], how="left").merge(lvl, on=["date", "zip"], how="left"))
    df["zip_code"] = pd.Categorical(df.zip, categories=zips)
    df["pred"] = m.predict(df[heat.FEATURES])
    x = df.copy()
    for c in heat.HEAT:
        x[c] = [norm[f"{p}|{mo}"][c] for p, mo in zip(x.point_id, x.month)]
    df["normal"] = m.predict(x[heat.FEATURES])
    df["excess"] = df.pred - df.normal
    pop = pd.read_parquet(PROCESSED / "acs_zcta.parquet").set_index("zip").population \
        if (PROCESSED / "acs_zcta.parquet").exists() else None
    cuts = thr.get("excess_per_10k")
    out = []
    for i, r in df.iterrows():
        # per-capita levels only where enough people live (campus / military ZIPs have few residents)
        per10k = float(r.excess / pop[r.zip] * 1e4) if pop is not None and pop.get(r.zip, 0) >= 1000 else None
        level = None
        if cuts and per10k is not None:
            level = "low" if per10k < cuts["moderate"] else "moderate" if per10k < cuts["high"] else \
                "high" if per10k < cuts["very_high"] else "very_high"
        out.append({"unit_id": r.zip, "target_date": f"{r.date:%Y-%m-%d}", "lead_days": int((r.date - today).days),
                    "value": round(float(r.excess), 2), "level": level,
                    "factors": top_factors("heat", m, df.loc[[i], heat.FEATURES], only=heat.HEAT),
                    "extra": {"expected_calls": round(float(r.pred), 1), "normal_calls": round(float(r.normal), 1),
                              "excess_per_10k": None if per10k is None else round(per10k, 3),
                              "tmax_f": None if pd.isna(r.tmax) else round(C_TO_F(r.tmax)),
                              "tmin_f": None if pd.isna(r.tmin) else round(C_TO_F(r.tmin))}})
    return out, df


# ---------------------------------------------------------------- Fire
FIRE_RADIUS_KM = 5.0


def predict_fire(now, wx, places):
    """Per place: the highest-risk 2 km cell within 5 km. Plus unit 'county': expected large fires county-wide."""
    art = ART / "fire"
    m = lgb.Booster(model_file=str(art / "model.txt"))
    cal = json.loads((art / "calibration.json").read_text())
    cuts = json.loads((art / "thresholds.json").read_text())["levels"]
    g = fire.grid()
    g = g[g.point_id.isin(wx)]
    today = local_today(now)
    pts = sorted(g.point_id.unique())
    seed_path = PROCESSED / "wet_dates.json"  # first run seeds from the ERA5 archive; later runs from saved state
    seed = json.loads(seed_path.read_text()) if seed_path.exists() else fire.wet_dates(pts)
    wet = fire.wet_dates(pts, source=wx, seed=seed)
    seed_path.write_text(json.dumps(wet))
    start = {p: wx[p].index.min().tz_convert(TZ).normalize().tz_localize(None) for p in pts}
    w = fire.weather_table(pts, source={p: wx[p] for p in pts},
                           last_rain={p: fire.last_rain_before(wet.get(p, []), start[p]) for p in pts})
    w = w[(w.date >= today) & (w.date < today + pd.Timedelta(days=4))]
    rows = g[["cell", "lat", "lon", "point_id", *fire.STATIC]].merge(w, on="point_id")
    rows["month"] = rows.date.dt.month
    rows["p"] = np.interp(m.predict(rows[fire.FEATURES]), cal["x"], cal["y"])
    rows["level"] = np.select([rows.p >= cuts["very_high"], rows.p >= cuts["high"], rows.p >= cuts["moderate"]],
                              ["very_high", "high", "moderate"], "low")
    out = []
    for d, day in rows.groupby("date"):
        k = int((d - today).days)
        out.append({"unit_id": "county", "target_date": f"{d:%Y-%m-%d}", "lead_days": k, "value": round(float(day.p.sum()), 3),
                    "level": None, "factors": [], "extra": {"share_cells_high": round(float(day.level.isin(["high", "very_high"]).mean()), 3)}})
        lat, lon = day.lat.to_numpy(), day.lon.to_numpy()
        for pl in places:
            km = 111 * np.hypot(lat - pl["lat"], (lon - pl["lon"]) * np.cos(np.radians(pl["lat"])))
            near = day[km <= FIRE_RADIUS_KM]
            if near.empty:
                continue
            top = near.loc[near.p.idxmax()]
            out.append({"unit_id": pl["id"], "target_date": f"{d:%Y-%m-%d}", "lead_days": k,
                        "value": round(float(top.p), 6), "level": top.level,
                        "factors": top_factors("fire", m, rows.loc[[top.name], fire.FEATURES],
                                               only=set(fire.FEATURES) - {"month"}),
                        "extra": {"cell": top.cell, "cells_nearby": int(len(near))}})
    return out, rows


# ---------------------------------------------------------------- Air
AIR_CATS = [(50, "good"), (100, "moderate"), (150, "usg"), (200, "unhealthy"), (300, "very_unhealthy")]


def aqi_category(v):
    return next((c for lim, c in AIR_CATS if v <= lim), "hazardous")


def predict_air(now, wx):
    """Daily AQI per AirNow monitor, days 0–3, PM2.5 and ozone. unit_id = '<pollutant>:<AQS site id>'."""
    art = ART / "air"
    obs = pd.read_parquet(PROCESSED / "airnow_obs.parquet").dropna(subset=["site", "parameter", "conc"])
    daily = air.daily_aqi_from_hourly(obs[["site", "parameter", "ts_utc", "conc"]])
    today = local_today(now)
    out, details = [], []
    for param in ("pm25", "ozone"):
        m50 = lgb.Booster(model_file=str(art / f"model_{param}_q50.txt"))
        m90 = lgb.Booster(model_file=str(art / f"model_{param}_q90.txt"))
        st = pd.DataFrame(json.loads((art / f"sites_{param}.json").read_text())).set_index("site")
        hist = daily[(daily.parameter == param) & daily.site.isin(st.index)][["site", "date", "aqi"]]
        cats = json.loads((art / f"site_categories_{param}.json").read_text())  # order = model's category codes
        trained = set(cats)
        # a monitor with no training-period data (e.g. one opened after 2023) has no learned site effect: skip it
        sites = [s for s in hist.site.unique() if s in trained and st.loc[s, "point_id"] in wx]
        if not sites:
            continue
        q = pd.DataFrame([(s, today + pd.Timedelta(days=k)) for s in sites for k in range(4)], columns=["site", "date"])
        wxd = {p: air.weather_daily(wx[p]) for p in st.loc[sites, "point_id"].unique()}
        rows = air.build(q, st, hist, wxd)
        rows = rows[rows.lead_k == (rows.date - today).dt.days].dropna(subset=["aqi_prev"])
        rows["site"] = pd.Categorical(rows.site.astype(str), categories=cats)
        rows["q50"], rows["q90"] = m50.predict(rows[air.FEATURES]), m90.predict(rows[air.FEATURES])
        for i, r in rows.iterrows():
            v = max(float(r.q50), 0)
            out.append({"unit_id": f"{param}:{r.site}", "target_date": f"{r.date:%Y-%m-%d}", "lead_days": int(r.lead_k),
                        "value": round(v, 1), "level": aqi_category(v),
                        "factors": top_factors("air", m50, rows.loc[[i], air.FEATURES], only=set(air.FEATURES) - {"site", "lead_k", "dow", "month"}),
                        "extra": {"parameter": param, "site": str(r.site), "site_name": st.loc[str(r.site), "name"],
                                  "lat": float(st.loc[str(r.site), "lat"]), "lon": float(st.loc[str(r.site), "lon"]),
                                  "high_end_aqi": round(max(float(r.q90), v), 1), "aqi_yesterday": float(r.aqi_prev)}})
        details.append(rows)
    return out, (pd.concat(details) if details else pd.DataFrame())
