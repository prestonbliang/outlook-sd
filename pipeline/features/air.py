"""Air features: one row per (monitor, pollutant, target date D, lead k = 0..3); issue date I = D − k.

Target: the day's AQI (EPA AirData: PM2.5 24-hour, ozone 8-hour max). Recent AQI uses days before I only;
weather is for the target day (archive for training, forecast at run time).
"""
import numpy as np
import pandas as pd

from pipeline.features.heat import daily_weather
from pipeline.sources import openmeteo
from pipeline.sources._common import PROCESSED

TZ = "America/Los_Angeles"
FEATURES = ["site", "lead_k", "aqi_prev", "aqi_prev_mean7", "tmax", "tmin", "rh_mean", "sw_sum", "wind_mean",
            "wind_max", "blh_max", "precip", "offshore_hours", "dow", "month"]


def labels(parameter):
    a = pd.read_parquet(PROCESSED / "airdata_daily.parquet")
    a = a[(a.parameter == parameter) & a.aqi.notna()]
    lab = a.groupby(["site_id", "date"]).aqi.max().reset_index().rename(columns={"site_id": "site"})
    lab["date"] = pd.to_datetime(lab.date)
    st = a.groupby("site_id").agg(lat=("lat", "first"), lon=("lon", "first"), name=("site_name", "first"))
    st["point_id"] = openmeteo.grid_id(st.lat, st.lon)[0]
    return lab, st


def weather_daily(hourly):
    """Daily target-day weather from hourly frame (ts_utc index)."""
    d = daily_weather(hourly)[["tmax", "tmin", "rh_mean"]]
    h = hourly.copy()
    h["date"] = pd.to_datetime(h.index.tz_convert(TZ).date)
    # Santa Ana / offshore flow: wind from the NE–E quadrant (20°–120°) at ≥ 4 m/s
    h["offshore"] = h.wind_direction_10m.between(20, 120) & (h.wind_speed_10m >= 4)
    g = h.groupby("date")
    d = d.join(pd.DataFrame({"sw_sum": g.shortwave_radiation.sum(), "wind_mean": g.wind_speed_10m.mean(),
                             "wind_max": g.wind_gusts_10m.max(), "blh_max": g.boundary_layer_height.max(),
                             "precip": g.precipitation.sum(), "offshore_hours": g.offshore.sum()}))
    return d


def build(lab, st, history, wx_by_point):
    """lab: (site, date[, aqi]) rows to build; history: observed (site, date, aqi) used for lagged AQI."""
    rows = lab.loc[lab.index.repeat(4)].reset_index(drop=True)
    rows["lead_k"] = np.tile(np.arange(4), len(lab))
    rows["issue"] = rows.date - pd.to_timedelta(rows.lead_k, unit="D")
    h = history.pivot_table(index="date", columns="site", values="aqi").asfreq("D")
    # A live issue date often follows the last complete AQI day. Extend the calendar,
    # never the values, so shifting yesterday's reading can reach today's issue row.
    if len(h.index) and len(rows):
        h = h.reindex(pd.date_range(min(h.index.min(), rows.issue.min()), max(h.index.max(), rows.issue.max()), freq="D"))
    prev = h.shift(1)  # day before issue
    mean7 = h.shift(1).rolling(7, min_periods=4).mean()
    idx = pd.MultiIndex.from_arrays([rows.issue, rows.site])
    rows["aqi_prev"] = prev.stack().reindex(idx).to_numpy()
    rows["aqi_prev_mean7"] = mean7.stack().reindex(idx).to_numpy()
    rows["point_id"] = rows.site.map(st.point_id)
    wcols = ["tmax", "tmin", "rh_mean", "sw_sum", "wind_mean", "wind_max", "blh_max", "precip", "offshore_hours"]
    parts = []
    for p, g in rows.groupby("point_id"):
        w = wx_by_point.get(p)
        if w is None:
            continue
        parts.append(pd.DataFrame(w.reindex(g.date)[wcols].to_numpy(), columns=wcols, index=g.index))
    rows = rows.join(pd.concat(parts))
    rows["dow"], rows["month"] = rows.date.dt.day_of_week, rows.date.dt.month
    rows["site"] = rows.site.astype("category")
    return rows


def training_table(parameter):
    lab, st = labels(parameter)
    wx = {}
    for p in st.point_id.unique():
        f = PROCESSED / f"weather_{p}.parquet"
        if f.exists():
            wx[p] = weather_daily(pd.read_parquet(f).set_index("ts_utc"))
    lab = lab[lab.site.map(st.point_id).isin(wx) & (lab.date >= "2014-01-15")]
    rows = build(lab, st, lab, wx)
    return rows.dropna(subset=["aqi_prev", "tmax"]), st


# EPA AQI breakpoints: (C_lo, C_hi, I_lo, I_hi). PM2.5 24-h µg/m³ (2024 revision); ozone 8-h ppm.
PM25_BP = [(0.0, 9.0, 0, 50), (9.1, 35.4, 51, 100), (35.5, 55.4, 101, 150), (55.5, 125.4, 151, 200),
           (125.5, 225.4, 201, 300), (225.5, 325.4, 301, 500)]
O3_8H_BP = [(0.000, 0.054, 0, 50), (0.055, 0.070, 51, 100), (0.071, 0.085, 101, 150), (0.086, 0.105, 151, 200),
            (0.106, 0.200, 201, 300)]


def aqi(conc, breakpoints, decimals):
    """EPA AQI from a concentration (truncated to the pollutant's reporting precision)."""
    if conc is None or np.isnan(conc):
        return np.nan
    c = np.floor(max(conc, 0) * 10 ** decimals) / 10 ** decimals
    for lo, hi, ilo, ihi in breakpoints:
        if c <= hi:
            return int(np.floor((ihi - ilo) / (hi - lo) * (max(c, lo) - lo) + ilo + 0.5))  # EPA rounds half up
    return breakpoints[-1][3]


def daily_aqi_from_hourly(obs):
    """AirNow hourly observations (site, ts_utc, parameter, raw concentration) → daily AQI per site and local date,
    computed like the AirData labels: PM2.5 = 24-h mean; ozone = daily max of the 8-h running mean (≥6 hours)."""
    out = []
    for (site, param), g in obs.groupby(["site", "parameter"]):
        s = g.set_index("ts_utc").conc.sort_index()
        s = s[~s.index.duplicated()].resample("h").mean()
        local = s.index.tz_convert(TZ).normalize().tz_localize(None)
        if param == "pm25":
            day = s.groupby(local).agg(["mean", "count"])
            vals = {d: aqi(r["mean"], PM25_BP, 1) for d, r in day.iterrows() if r["count"] >= 18}
        else:
            run8 = s.rolling(8, min_periods=6).mean() / 1000  # ppb → ppm
            vals = {d: aqi(v, O3_8H_BP, 3) for d, v in run8.groupby(local).max().items() if pd.notna(v)}
        out += [{"site": site, "parameter": param, "date": d, "aqi": v} for d, v in vals.items()]
    return pd.DataFrame(out, columns=["site", "parameter", "date", "aqi"])
