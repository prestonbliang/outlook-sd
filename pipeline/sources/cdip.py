"""CDIP wave buoys via CeNCOOS ERDDAP: 191 Point Loma South (live), 155 Imperial Beach (history, ends May 2026)."""
import io

import pandas as pd

from ._common import get, upsert

ERDDAP = "https://erddap.cencoos.org/erddap/tabledap/edu_ucsd_cdip_{st}.csv"
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


def fetch_live():
    return upsert(fetch("191", pd.Timestamp.utcnow() - pd.Timedelta(days=3)), "cdip_191", ["ts_utc"])
