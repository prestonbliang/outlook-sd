"""AirNow API (EPA): live hourly observations in the county and the official AQI forecast (our baseline)."""
import os

import pandas as pd

from ._common import BBOX, PROCESSED, get, now_utc, upsert

BASE = "https://www.airnowapi.org/aq"
# Keyless public hourly files with the same monitor readings: backup when the API is down or no key is set.
FILES = "https://files.airnowtech.org/airnow/{t:%Y}/{t:%Y%m%d}/HourlyData_{t:%Y%m%d%H}.dat"


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


def observations_from_files(hours=48):
    """date|time (UTC)|AQS id|site|GMT offset|parameter|units|value|agency. PM2.5 in µg/m³ and ozone in ppb, as the API."""
    end = now_utc().replace(minute=0, second=0, microsecond=0) - pd.Timedelta(hours=1)
    rows = []
    for t in pd.date_range(end - pd.Timedelta(hours=hours - 1), end, freq="h"):
        try:
            text = get("airnow_files", FILES.format(t=t), save=False, timeout=60).text
        except RuntimeError:
            continue  # an hour not yet published
        rows += [ln.split("|") for ln in text.splitlines() if ln.count("|") >= 7 and ln.split("|")[2].startswith("06073")]
    df = pd.DataFrame(rows).iloc[:, :8] if rows else pd.DataFrame(columns=range(8))
    df.columns = ["date", "time", "site", "SiteName", "offset", "Parameter", "units", "value"]
    df = df[df.Parameter.isin(["PM2.5", "OZONE"])]
    df["ts_utc"] = pd.to_datetime(df.date + " " + df.time, format="%m/%d/%y %H:%M", utc=True)
    df["parameter"] = df.Parameter.map({"PM2.5": "pm25", "OZONE": "ozone"})
    df["conc"] = pd.to_numeric(df.value, errors="coerce").where(lambda v: v >= 0)
    df["AQI"], df["Latitude"], df["Longitude"] = float("nan"), float("nan"), float("nan")
    df["tz_source"] = "UTC (AirNow public hourly files)"
    return df[["ts_utc", "site", "SiteName", "Parameter", "parameter", "conc", "AQI", "Latitude", "Longitude", "tz_source"]]


def forecast(lat, lon):
    """Official forecast for the nearest Reporting Area. /forecast/latLong/ was retired Sep 30, 2026; this replaces it."""
    params = {"format": "application/json", "latitude": lat, "longitude": lon, "API_KEY": _key()}
    return pd.DataFrame(get("airnow_forecast", f"{BASE}/forecast/current/", params, ext="json").json())


def fetch_live(lat=32.7157, lon=-117.1611):
    have = PROCESSED / "airnow_obs.parquet"
    hours = 48 if have.exists() else 8 * 24  # first run: 8 days so the 7-day mean exists
    try:
        obs = observations(hours)
    except RuntimeError as e:  # API down or no key: same readings from the public files; the official forecast is skipped
        print(f"[airnow] API unavailable, using public hourly files: {str(e)[:120]}")
        obs = observations_from_files(hours)
        if len(obs):
            upsert(obs, "airnow_obs", ["ts_utc", "site", "parameter"])
        return obs, pd.DataFrame()
    if len(obs):
        upsert(obs, "airnow_obs", ["ts_utc", "site", "parameter"])
    fc = forecast(lat, lon)
    if len(fc):
        fc["fetched_utc"] = now_utc()
        upsert(fc, "airnow_forecast_log", ["dateIssue", "dateValid", "reportingArea", "parameterName"])
    return obs, fc
