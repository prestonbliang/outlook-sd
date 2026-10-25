"""CDIP wave buoys via CeNCOOS ERDDAP: 191 Point Loma South (live), 155 Imperial Beach (history, ends May 2026)."""
import io

import pandas as pd

from ._common import PROCESSED, get, upsert

ERDDAP = "https://erddap.cencoos.org/erddap/tabledap/edu_ucsd_cdip_{st}.csv"
# The same physical buoy (CDIP 191 = NDBC 46232), republished by NOAA: backup when ERDDAP is down.
NDBC_191 = "https://www.ndbc.noaa.gov/data/realtime2/46232.txt"
VARS = {"sea_surface_wave_significant_height": "hs_m",
        "sea_surface_wave_period_at_variance_spectral_density_maximum": "tp_s",
        "sea_surface_wave_from_direction": "dp_deg",
        "sea_water_temperature": "sst_c"}
GOOD_QC = {1, 2}  # PASS, NOT_EVALUATED (from .das flag_meanings); SUSPECT/FAIL/MISSING are dropped


def fetch(station, start):
    cols = ["time"] + [x for v in VARS for x in (v, f"{v}_qc_agg")]
    url = ERDDAP.format(st=station) + "?" + ",".join(cols) + f"&time%3E={pd.Timestamp(start):%Y-%m-%dT%H:%M:%SZ}"
    r = get(f"cdip_{station}", url, ext="csv", timeout=600)
    df = pd.read_csv(io.StringIO(r.text), skiprows=[1])  # row 1 holds units
    for v, short in VARS.items():
        df[short] = df[v].where(df[f"{v}_qc_agg"].isin(GOOD_QC))
    df["ts_utc"] = pd.to_datetime(df.time, utc=True)
    df["station"], df["tz_source"] = str(station), "UTC"
    return df[["ts_utc", "station", *VARS.values(), "tz_source"]].dropna(subset=list(VARS.values()), how="all")


def fetch_history(start="2010-01-01"):
    for st in ("191", "155"):
        upsert(fetch(st, start), f"cdip_{st}", ["ts_utc"])


def parse_ndbc(text):
    """NDBC realtime2 standard met: WVHT (m), DPD = peak period (s), MWD = direction at DPD (°), WTMP (°C); MM = missing."""
    rows = [ln.split() for ln in text.splitlines() if ln and not ln.startswith("#")]
    df = pd.DataFrame(rows, columns=text.splitlines()[0].lstrip("#").split()).replace("MM", None)
    df["ts_utc"] = pd.to_datetime(df.YY + "-" + df.MM + "-" + df.DD + " " + df.hh + ":" + df.mm, utc=True)
    out = pd.DataFrame({"ts_utc": df.ts_utc, "station": "191"})
    for col, short in {"WVHT": "hs_m", "DPD": "tp_s", "MWD": "dp_deg", "WTMP": "sst_c"}.items():
        out[short] = pd.to_numeric(df[col], errors="coerce")
    out["tz_source"] = "UTC (NDBC 46232 copy)"
    return out.dropna(subset=list(VARS.values()), how="all")


def fetch_live():
    try:
        df = fetch("191", pd.Timestamp.utcnow() - pd.Timedelta(days=3))
    except RuntimeError as e:
        print(f"[cdip] ERDDAP unavailable, using NOAA's copy of the same buoy: {str(e)[:120]}")
        df = parse_ndbc(get("cdip_191", NDBC_191).text)
        stored = PROCESSED / "cdip_191.parquet"
        if stored.exists():  # only fill the gap: the two feeds log the same waves at different minutes
            have = pd.read_parquet(stored, columns=["ts_utc", "tz_source"])
            df = df[df.ts_utc > have[have.tz_source == "UTC"].ts_utc.max()]
    return upsert(df, "cdip_191", ["ts_utc"])
