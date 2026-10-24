"""NASA FIRMS active-fire detections (VIIRS 375 m) over San Diego County. Needs FIRMS_MAP_KEY."""
import io
import os

import pandas as pd

from ._common import BBOX, get, upsert

AREA = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/{bbox}/{days}"


def _fetch(source, days, date=None):
    key = os.environ.get("FIRMS_MAP_KEY")
    if not key:
        raise RuntimeError("FIRMS_MAP_KEY is not set (.env)")
    url = AREA.format(key=key, source=source, bbox=",".join(map(str, BBOX)), days=days)
    if date:
        url += f"/{pd.Timestamp(date):%Y-%m-%d}"
    text = get("firms", url, ext="csv", timeout=300).text
    if text.startswith("Invalid") or "error" in text[:200].lower():
        raise RuntimeError(f"firms {source} {date}: {text[:200]}")
    df = pd.read_csv(io.StringIO(text))
    if len(df):
        df["ts_utc"] = pd.to_datetime(df.acq_date + " " + df.acq_time.astype(str).str.zfill(4), format="%Y-%m-%d %H%M", utc=True)
        df["product"], df["tz_source"] = source, "UTC"
    return df


def fetch_live():
    df = _fetch("VIIRS_SNPP_NRT", 3)
    return upsert(df, "firms", ["ts_utc", "latitude", "longitude"]) if len(df) else df


def fetch_history(start="2014-01-01", end=None):
    """10-day chunks: standard-processing archive (SP), then NRT for the most recent months."""
    end = pd.Timestamp(end or pd.Timestamp.utcnow().date())
    for t in pd.date_range(start, end, freq="10D"):
        df = _fetch("VIIRS_SNPP_SP", 10, t)
        if not len(df):
            df = _fetch("VIIRS_SNPP_NRT", 10, t)
        if len(df):
            upsert(df, "firms", ["ts_utc", "latitude", "longitude"])
