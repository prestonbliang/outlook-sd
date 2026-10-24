"""Flood features: one row per (issue time, lead hour 1–72). Target = tide residual at issue + lead (STND ft).

Leakage rule: tide/residual/wave/SST features use only observations at or before the issue time; weather is
taken at the target hour (archive = 'perfect forecast' for training, forecast or previous-runs at inference/hindcast).
"""
import numpy as np
import pandas as pd

from pipeline.sources._common import PROCESSED

STATION = "9410170"
POINT = "g32.75_-117.25"  # ERA5 grid point nearest the San Diego gauge
LEADS = np.arange(1, 73)
WX = ["surface_pressure", "wind_speed_10m", "wind_gusts_10m", "u10", "v10"]
FEATURES = ["lead_h", "tide_pred", "resid_now", "resid_mean_24h", "resid_mean_7d", "pressure", "pressure_change",
            "wind_speed_10m", "wind_gusts_10m", "u10", "v10", "hs_now", "tp_now", "sst_anom", "doy_sin", "doy_cos"]


def load_tides():
    t = pd.read_parquet(PROCESSED / f"tides_{STATION}.parquet").set_index("ts_utc").sort_index()
    return t[~t.index.duplicated()]


def add_wind_components(w):
    rad = np.deg2rad(w.wind_direction_10m)  # direction the wind comes FROM
    w["u10"] = -w.wind_speed_10m * np.sin(rad)  # eastward
    w["v10"] = -w.wind_speed_10m * np.cos(rad)  # northward
    return w


def load_weather():
    w = pd.read_parquet(PROCESSED / f"weather_{POINT}.parquet").set_index("ts_utc").sort_index()
    return add_wind_components(w)


def load_waves():
    c = pd.read_parquet(PROCESSED / "cdip_191.parquet").set_index("ts_utc").sort_index()
    h = c[["hs_m", "tp_s", "sst_c"]].resample("h").mean()
    clim = h.sst_c.groupby(h.index.month).transform("mean")  # monthly climatology over the full record
    h["sst_anom"] = h.sst_c - clim
    return h


def state_at(tides, waves, issue_times):
    """Observed state at each issue time (only data ≤ issue)."""
    r = tides.residual_ft
    s = pd.DataFrame(index=issue_times)
    s["resid_now"] = r.ffill(limit=3).reindex(issue_times)
    s["resid_mean_24h"] = r.rolling("24h").mean().reindex(issue_times)
    s["resid_mean_7d"] = r.rolling("7D").mean().reindex(issue_times)
    wv = waves.ffill(limit=6).reindex(issue_times)
    s["hs_now"], s["tp_now"], s["sst_anom"] = wv.hs_m, wv.tp_s, wv.sst_anom
    return s


def build(issue_times, tides, weather, waves, pressure_now=None):
    """weather: hourly frame indexed by target time with WX columns (archive, forecast or previous runs)."""
    s = state_at(tides, waves, issue_times)
    rows = pd.DataFrame({"issue": np.repeat(issue_times, len(LEADS)), "lead_h": np.tile(LEADS, len(issue_times))})
    rows["target"] = rows.issue + pd.to_timedelta(rows.lead_h, unit="h")
    rows = rows.join(s, on="issue")
    rows["tide_pred"] = tides.predicted_ft.reindex(rows.target).to_numpy()
    rows["residual"] = tides.residual_ft.reindex(rows.target).to_numpy()
    rows["observed"] = tides.observed_ft.reindex(rows.target).to_numpy()
    wx = weather.reindex(rows.target)
    for c in WX:
        rows[c] = wx[c].to_numpy()
    rows["pressure"] = rows.pop("surface_pressure")
    p_now = (pressure_now if pressure_now is not None else weather.surface_pressure).reindex(rows.issue).to_numpy()
    rows["pressure_change"] = rows.pressure - p_now
    doy = rows.target.dt.day_of_year
    rows["doy_sin"], rows["doy_cos"] = np.sin(2 * np.pi * doy / 365.25), np.cos(2 * np.pi * doy / 365.25)
    return rows


def training_table():
    tides, weather, waves = load_tides(), load_weather(), load_waves()
    end = min(weather.index.max(), tides.observed_ft.dropna().index.max()) - pd.Timedelta(hours=72)
    issues = pd.date_range(pd.Timestamp("2014-01-08", tz="UTC"), end.floor("12h"), freq="12h")  # 00z and 12z
    return build(issues, tides, weather, waves).dropna(subset=["residual"])
