"""AirNow API (EPA): live hourly observations in the county and the official AQI forecast (our baseline)."""
import os

import pandas as pd

from ._common import BBOX, PROCESSED, get, now_utc, upsert

BASE = "https://www.airnowapi.org/aq"


def _key():
    key = os.environ.get("AIRNOW_API_KEY")
    if not key:
        raise RuntimeError("AIRNOW_API_KEY is not set (.env)")
    return key


def observations(hours=48):
    end = now_utc()
    w, s, e, n = BBOX
    js = get("airnow_obs", f"{BASE}/data/", {
        "startDate": f"{end - pd.Timedelta(hours=hours):%Y-%m-%dT%H}", "endDate": f"{end:%Y-%m-%dT%H}",
        "parameters": "OZONE,PM25", "BBOX": f"{w},{s},{e},{n}", "dataType": "B", "format": "application/json",
        "verbose": 1, "API_KEY": _key()}, ext="json").json()
    df = pd.DataFrame(js)
    if len(df):
        df["ts_utc"] = pd.to_datetime(df.UTC, utc=True)
        df["tz_source"] = "UTC"
        # normalized columns: AQS site id (state+county+site, as in EPA AirData), pollutant, raw concentration
        df["site"] = df.FullAQSCode.astype(str).str[-9:] if "FullAQSCode" in df else df.IntlAQSCode.astype(str).str[-9:]
        df["parameter"] = df.Parameter.map({"PM2.5": "pm25", "OZONE": "ozone"})
        raw = df.RawConcentration if "RawConcentration" in df else df.Value
        df["conc"] = pd.to_numeric(raw, errors="coerce").where(lambda v: v >= 0)
    return df


def forecast(lat, lon, date=None):
    params = {"format": "application/json", "latitude": lat, "longitude": lon, "distance": 25, "API_KEY": _key()}
    if date:
        params["date"] = f"{pd.Timestamp(date):%Y-%m-%d}"
    return pd.DataFrame(get("airnow_forecast", f"{BASE}/forecast/latLong/", params, ext="json").json())


def fetch_live(lat=32.7157, lon=-117.1611):
    have = PROCESSED / "airnow_obs.parquet"
    obs = observations(hours=48 if have.exists() else 8 * 24)  # first run: 8 days so the 7-day mean exists
    if len(obs):
        upsert(obs, "airnow_obs", ["ts_utc", "site", "parameter"])
    fc = forecast(lat, lon)
    if len(fc):
        fc["fetched_utc"] = now_utc()
        upsert(fc, "airnow_forecast_log", ["DateIssue", "DateForecast", "ReportingArea", "ParameterName"])
    return obs, fc
