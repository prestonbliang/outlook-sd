"""Water features: one row per (station, sample date D, lead k = 0..3); issue date I = D − k.

Label: enterococcus above the state single-sample standard — 104 per 100 mL for culture methods (MPN/CFU),
1,413 DNA copies per 100 mL for ddPCR (San Diego County since May 2022; Crain et al. 2021, EPA Region 9).
Features use observations through the day before I (flow, observed rain, waves, SST) and forecast rain for I..D.
Last-sample features are deliberately excluded: Beach Watch lags months, so they would not exist at forecast time.
"""
import numpy as np
import pandas as pd

from pipeline.sources import openmeteo
from pipeline.sources._common import PROCESSED

TZ = "America/Los_Angeles"
MOUTH = (32.5565, -117.1278)  # Tijuana River mouth
SOUTH_BAY_KM = 15
THRESHOLD = {"MPN/100ml": 104.0, "CFU/100ml": 104.0, "Copies/100ml": 1413.0}
FEATURES = ["station", "lead_k", "dist_mouth_km", "q_24h", "q_72h", "q_7d", "q_max_7d", "rain_24h", "rain_72h",
            "rain_fcst", "hs", "tp", "dp", "sst", "tide_max", "month"]


def haversine_km(lat, lon, lat0, lon0):
    p = np.pi / 180
    a = (np.sin((lat - lat0) * p / 2) ** 2
         + np.cos(lat * p) * np.cos(lat0 * p) * np.sin((lon - lon0) * p / 2) ** 2)
    return 12742 * np.arcsin(np.sqrt(a))


def labels():
    r = pd.read_parquet(PROCESSED / "beach_results.parquet")
    r = r[r.SampleType.isin(["Results", "Duplicate"]) & r.Unit.isin(THRESHOLD) & r.Result.notna()]
    thr = r.Unit.map(THRESHOLD)
    r = r.assign(ratio=r.Result / thr, date=pd.to_datetime(r.date), station=r.Station_id.astype(str),
                 lat=pd.to_numeric(r.Station_UpperLat), lon=pd.to_numeric(r.Station_UpperLon))
    r["exceed"] = (r.Result > thr) | ((r.Qualifier == ">") & (r.Result >= thr))
    lab = r.groupby(["station", "date"]).agg(exceed=("exceed", "max"), ratio=("ratio", "max")).reset_index()
    st = r.groupby("station").agg(lat=("lat", "median"), lon=("lon", "median"), name=("Station_Name", "first"),
                                  beach=("Beach_Name", "first"), waterbody=("WaterBodyType", "first"))
    st = st.dropna(subset=["lat", "lon"])
    st["dist_mouth_km"] = haversine_km(st.lat, st.lon, *MOUTH)
    st["south_bay"] = st.dist_mouth_km <= SOUTH_BAY_KM
    st["point_id"] = openmeteo.grid_id(st.lat, st.lon)[0]
    return lab[lab.station.isin(st.index)], st


def daily_local(series, how):
    s = series.copy()
    s.index = s.index.tz_convert(TZ).tz_localize(None)
    return getattr(s.resample("D"), how)()


def flow_daily():
    f = pd.read_parquet(PROCESSED / "ibwc_flow.parquet").set_index("ts_utc").sort_index().discharge_m3s
    f = f.resample("h").mean()
    return pd.DataFrame({"mean": daily_local(f, "mean"), "max": daily_local(f, "max"),
                         "n": daily_local(f.notna().astype(float), "sum")})


def flow_features(fd):
    """Indexed by issue date I: flow statistics over the days before I (m³/s). NaN where the gauge has gaps."""
    m = fd["mean"].where(fd.n >= 12)
    out = pd.DataFrame(index=fd.index)
    out["q_24h"] = m.shift(1)
    out["q_72h"] = m.shift(1).rolling(3, min_periods=3).mean()
    out["q_7d"] = m.shift(1).rolling(7, min_periods=6).mean()
    out["q_max_7d"] = fd["max"].where(fd.n >= 12).shift(1).rolling(7, min_periods=6).max()
    return out


def rain_daily(point_id, source=None):
    h = source if source is not None else pd.read_parquet(PROCESSED / f"weather_{point_id}.parquet").set_index("ts_utc")
    return daily_local(h.precipitation, "sum")  # mm


def waves_daily():
    c = pd.read_parquet(PROCESSED / "cdip_191.parquet").set_index("ts_utc").sort_index()
    rad = np.deg2rad(c.dp_deg)
    d = pd.DataFrame({"hs": daily_local(c.hs_m, "mean"), "tp": daily_local(c.tp_s, "mean"),
                      "sst": daily_local(c.sst_c, "mean"),
                      "dp": np.rad2deg(np.arctan2(daily_local(np.sin(rad), "mean"), daily_local(np.cos(rad), "mean"))) % 360})
    return d


def tide_daily():
    t = pd.read_parquet(PROCESSED / "tides_9410170.parquet").set_index("ts_utc").predicted_ft
    return daily_local(t, "max")


def build(lab, st, fd, waves, tide, rain_by_point):
    rows = lab.loc[lab.index.repeat(4)].reset_index(drop=True)
    rows["lead_k"] = np.tile(np.arange(4), len(lab))
    rows["issue"] = rows.date - pd.to_timedelta(rows.lead_k, unit="D")
    rows = rows.join(st[["dist_mouth_km", "south_bay", "point_id"]], on="station")
    rows = rows.join(flow_features(fd), on="issue")
    wv = waves.shift(1)  # observed through the day before issue
    rows = rows.join(wv, on="issue")
    rows["tide_max"] = tide.reindex(rows.date).to_numpy()
    rain_cols = []
    for p, g in rows.groupby("point_id"):
        r = rain_by_point[p]
        c = r.cumsum()
        obs24 = r.shift(1).reindex(g.issue).to_numpy()
        obs72 = r.shift(1).rolling(3).sum().reindex(g.issue).to_numpy()
        fc = c.reindex(g.date).to_numpy() - c.shift(1).reindex(g.issue).to_numpy()  # rain on days I..D
        rain_cols.append(pd.DataFrame({"rain_24h": obs24, "rain_72h": obs72, "rain_fcst": fc}, index=g.index))
    rows = rows.join(pd.concat(rain_cols))
    rows["month"] = rows.date.dt.month
    rows["station"] = rows.station.astype("category")
    return rows


def training_table():
    lab, st = labels()
    points = {p: rain_daily(p) for p in st.point_id.unique() if (PROCESSED / f"weather_{p}.parquet").exists()}
    st = st[st.point_id.isin(points)]
    lab = lab[lab.station.isin(st.index) & (lab.date >= "2014-01-08")]
    rows = build(lab, st, flow_daily(), waves_daily(), tide_daily(), points)
    return rows.dropna(subset=["q_7d", "rain_72h"]), st
