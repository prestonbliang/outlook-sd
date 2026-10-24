"""Open-Meteo: ERA5 archive (training), forecast (inference), previous runs (honest hindcasts).

Weather is pulled on the ERA5 0.25° grid; every station / ZIP / fire cell maps to its nearest grid point.
Archive and forecast use the same 10 variables (≤10 keeps each 2-week block at one API-call unit).
"""
import time

import numpy as np
import pandas as pd

from ._common import BBOX, PROCESSED, get, now_utc

VARS = ["temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation", "wind_speed_10m",
        "wind_direction_10m", "wind_gusts_10m", "surface_pressure", "boundary_layer_height", "shortwave_radiation"]
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"
PREVIOUS = "https://previous-runs-api.open-meteo.com/v1/forecast"


def grid_id(lat, lon):
    """Snap to the ERA5 0.25° grid; returns (id, lat, lon)."""
    glat, glon = np.round(np.asarray(lat) * 4) / 4, np.round(np.asarray(lon) * 4) / 4
    return [f"g{a:.2f}_{b:.2f}" for a, b in zip(glat, glon)], glat, glon


def grid_points():
    """All ERA5 grid points whose centres fall in (or within one cell of) the county bbox."""
    w, s, e, n = BBOX
    lats = np.arange(np.floor(s * 4) / 4, np.ceil(n * 4) / 4 + 0.01, 0.25)
    lons = np.arange(np.floor(w * 4) / 4, np.ceil(e * 4) / 4 + 0.01, 0.25)
    pts = [(a, b) for a in lats for b in lons]
    ids, la, lo = grid_id([p[0] for p in pts], [p[1] for p in pts])
    return pd.DataFrame({"point_id": ids, "lat": la, "lon": lo})


def _request(source, url, params, tries=6):
    for i in range(tries):
        try:
            return get(source, url, params, ext="json", timeout=300).json()
        except RuntimeError as e:
            if "HTTP 429" not in str(e) or i == tries - 1:
                raise
            time.sleep(60 * (i + 1))  # rate limit: back off and retry


def _frame(js, point_id, hourly_vars):
    df = pd.DataFrame(js["hourly"])
    df["ts_utc"] = pd.to_datetime(df.pop("time"), utc=True)
    df["point_id"], df["tz_source"] = point_id, "UTC"
    return df[["ts_utc", "point_id", *hourly_vars, "tz_source"]]


def archive(point_id, lat, lon, start, end):
    js = _request("openmeteo_archive", ARCHIVE, {
        "latitude": lat, "longitude": lon, "start_date": start, "end_date": end, "hourly": ",".join(VARS),
        "models": "era5", "timezone": "UTC", "wind_speed_unit": "ms"})
    return _frame(js, point_id, VARS)


def fetch_history(points, start="2010-01-01", end=None):
    """points: DataFrame point_id, lat, lon. Writes processed/weather_<point_id>.parquet; skips points already done."""
    end = end or (now_utc() - pd.Timedelta(days=6)).strftime("%Y-%m-%d")  # ERA5 lags ~5 days
    for p in points.itertuples():
        out = PROCESSED / f"weather_{p.point_id}.parquet"
        if out.exists():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        archive(p.point_id, p.lat, p.lon, start, end).to_parquet(out, index=False)
        print(f"weather {p.point_id}: {start} → {end}")


def forecast(points, days=4, past_days=7):
    """Live forecast (plus recent past) for all points in one multi-location call per 100 points."""
    frames = []
    for i in range(0, len(points), 100):
        chunk = points.iloc[i:i + 100]
        js = _request("openmeteo_forecast", FORECAST, {
            "latitude": ",".join(map(str, chunk.lat)), "longitude": ",".join(map(str, chunk.lon)),
            "hourly": ",".join(VARS), "forecast_days": days, "past_days": past_days,
            "timezone": "UTC", "wind_speed_unit": "ms"})
        js = js if isinstance(js, list) else [js]
        frames += [_frame(loc, pid, VARS) for pid, loc in zip(chunk.point_id, js)]
    return pd.concat(frames, ignore_index=True)


def previous_runs(point_id, lat, lon, start, end, leads=(1, 2, 3)):
    """Archived forecasts issued `lead` days before each hour — for leakage-free hindcasts."""
    hv = [f"{v}_previous_day{d}" for d in leads for v in VARS]
    js = _request("openmeteo_previous", PREVIOUS, {
        "latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
        "hourly": ",".join(hv), "timezone": "UTC", "wind_speed_unit": "ms"})
    return _frame(js, point_id, hv)
