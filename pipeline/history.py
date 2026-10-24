"""make history: download and process every source into data/processed/. Usage: python -m pipeline.history [source ...]"""
import sys

import numpy as np
import pandas as pd

from .sources import (airdata, beachwatch, calfire, cdip, fpa_fod, geo, ibwc, noaa_tides, nws, openmeteo,
                      sd_fire_ems)
from .sources._common import PROCESSED

WEATHER_START = "2014-01-01"


def weather():
    path = PROCESSED / "weather_points.csv"
    if not path.exists():
        PROCESSED.mkdir(parents=True, exist_ok=True)
        openmeteo.grid_points().to_csv(path, index=False)
    pts = pd.read_csv(path)
    # coastal/urban points first (Flood, Water, Heat, Air); east-county points are needed only by Fire
    pts = pts.iloc[np.argsort(np.hypot(pts.lat - 32.72, pts.lon + 117.16))]
    openmeteo.fetch_history(pts, start=WEATHER_START)


def previous_runs():
    """Archived day-1/2/3 forecasts at the tide-gauge point for the Flood forecast-input hindcast (test years)."""
    out = PROCESSED / "previous_runs_g32.75_-117.25.parquet"
    if not out.exists():
        end = (pd.Timestamp.utcnow() - pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        openmeteo.previous_runs("g32.75_-117.25", 32.75, -117.25, "2025-01-01", end).to_parquet(out, index=False)


def static_geo():
    geo.fetch_history()
    geo.write_places_json()
    geo.roads()
    geo.fhsz()


STEPS = {
    "geo": static_geo,
    "acs": lambda: geo.acs(geo.zcta().zip.tolist()),
    "weather": weather,
    "previous_runs": previous_runs,
    "tides": lambda: noaa_tides.fetch_history(start=WEATHER_START),
    "cdip": cdip.fetch_history,
    "ibwc": ibwc.fetch_history,
    "nws": nws.fetch_history,
    "beachwatch": beachwatch.fetch_history,
    "ems": sd_fire_ems.fetch_history,
    "airdata": airdata.fetch_history,
    "calfire": calfire.fetch_history,
    "fpa_fod": fpa_fod.fetch_history,
}

if __name__ == "__main__":
    for name in sys.argv[1:] or STEPS:
        print(f"== {name}", flush=True)
        STEPS[name]()
