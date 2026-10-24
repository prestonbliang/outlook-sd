"""EPA AirData pre-generated daily files (PM2.5 FRM/FEM 88101, ozone 44201), filtered to San Diego County (06/073)."""
import io

import pandas as pd

from ._common import RAW, get, write

URL = "https://aqs.epa.gov/aqsweb/airdata/daily_{param}_{year}.zip"
PARAMS = {"88101": "pm25", "44201": "ozone"}


def year(param, yr):
    """National zip is read in memory; only the San Diego rows are kept on disk (data/raw/airdata/)."""
    out = RAW / "airdata" / f"daily_{param}_{yr}_sd.csv"
    if not out.exists() or yr >= pd.Timestamp.now().year - 1:
        r = get("airdata", URL.format(param=param, year=yr), save=False, timeout=900)
        df = pd.read_csv(io.BytesIO(r.content), compression="zip", low_memory=False, dtype={"State Code": str, "County Code": str})
        df = df[(df["State Code"] == "06") & (df["County Code"] == "073")]
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
    return pd.read_csv(out, dtype={"State Code": str, "County Code": str, "Site Num": str})


def fetch_history(years=range(2010, 2027)):
    frames = []
    for param, name in PARAMS.items():
        for yr in years:
            d = year(param, yr)
            frames.append(pd.DataFrame({
                "date": pd.to_datetime(d["Date Local"]).dt.date,
                "site_id": d["State Code"] + d["County Code"] + d["Site Num"].str.zfill(4),
                "poc": d["POC"], "lat": d["Latitude"], "lon": d["Longitude"], "parameter": name,
                "duration": d["Sample Duration"], "aqi": d["AQI"], "value": d["Arithmetic Mean"],
                "max_value": d["1st Max Value"], "units": d["Units of Measure"], "site_name": d["Local Site Name"],
                "tz_source": "local standard time (date only)"}))
    df = pd.concat(frames, ignore_index=True)
    return write(df, "airdata_daily")
