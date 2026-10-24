"""Fire features: one row per (2 km cell, local date). Label: a new fire starts in the cell and reaches ≥10 acres.

Labels: FPA FOD (2014–2020, exact ignition points) and, from 2021, CAL FIRE incidents plus FRAP perimeter
centroids (approximate origins), de-duplicated. Static cell features use only pre-2014 fire history, so they cannot
leak into the 2014+ training and test years. Weather is the cell's nearest ERA5 point, for the target day.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from pipeline.features.air import weather_daily
from pipeline.sources import geo, openmeteo
from pipeline.sources._common import PROCESSED

TZ = "America/Los_Angeles"
CELL_M = 2000
MIN_ACRES = 10
FHSZ_RANK = {"Moderate": 1, "High": 2, "Very High": 3}
STATIC = ["fhsz_very_high", "fhsz_high", "fires_1990_2013", "dist_road_km"]
WEATHER = ["tmax", "rh_min", "wind_max", "wind_mean", "offshore_hours", "days_since_rain", "precip"]
FEATURES = [*STATIC, *WEATHER, "month"]


def grid():
    """2 km cells (EPSG:3310) covering county land; cached in processed/fire_grid.parquet."""
    path = PROCESSED / "fire_grid.parquet"
    if path.exists():
        return gpd.read_parquet(path)
    county = geo.county().to_crs(3310).union_all()
    x0, y0, x1, y1 = county.bounds
    cells = [box(x, y, x + CELL_M, y + CELL_M) for x in np.arange(x0, x1, CELL_M) for y in np.arange(y0, y1, CELL_M)]
    g = gpd.GeoDataFrame(geometry=cells, crs=3310)
    g = g[g.intersects(county)].reset_index(drop=True)
    g["cell"] = [f"c{i:05d}" for i in range(len(g))]
    c = g.centroid.to_crs(4326)
    g["lat"], g["lon"] = c.y, c.x
    g["point_id"] = openmeteo.grid_id(g.lat, g.lon)[0]
    g = add_static(g)
    g.to_parquet(path)
    return g


def add_static(g):
    fh = gpd.read_parquet(PROCESSED / "fhsz_sd.parquet").to_crs(3310)
    fh["geometry"] = fh.make_valid()  # simplified on download (maxAllowableOffset), so repair before overlay
    fh = fh.explode(index_parts=False)
    fh = fh[fh.geom_type.isin(["Polygon", "MultiPolygon"])]  # make_valid can add stray lines/points
    ov = gpd.overlay(g[["cell", "geometry"]], fh[["FHSZ", "geometry"]], how="intersection", keep_geom_type=True)
    share = (ov.area.groupby([ov.cell, ov.FHSZ]).sum() / (CELL_M ** 2)).unstack(fill_value=0)
    for cls, col in [("Very High", "fhsz_very_high"), ("High", "fhsz_high")]:
        g[col] = g.cell.map(share[cls] if cls in share else {}).fillna(0).clip(upper=1)
    per = gpd.read_parquet(PROCESSED / "calfire_perimeters.parquet")
    per = gpd.GeoDataFrame(per, geometry="geometry", crs=4326).to_crs(3310)
    per = per[pd.to_numeric(per.YEAR_, errors="coerce").between(1990, 2013)]
    hits = gpd.sjoin(g[["cell", "geometry"]], per[["geometry"]], predicate="intersects")
    g["fires_1990_2013"] = g.cell.map(hits.groupby("cell").size()).fillna(0)
    roads = gpd.read_parquet(PROCESSED / "roads_sd.parquet").to_crs(3310).union_all()
    g["dist_road_km"] = g.centroid.distance(roads) / 1000
    return g


def starts():
    """Fire starts ≥ MIN_ACRES: date (local), lat, lon, acres, source."""
    f = pd.read_parquet(PROCESSED / "fpa_fod_sd.parquet")
    f = f[(f.FIRE_SIZE >= MIN_ACRES) & (f.FIRE_YEAR >= 2014)]
    fpa = pd.DataFrame({"date": pd.to_datetime(f.DISCOVERY_DATE, format="mixed"), "lat": f.LATITUDE, "lon": f.LONGITUDE,
                        "acres": f.FIRE_SIZE, "name": f.FIRE_NAME, "source": "FPA FOD"})
    inc = pd.read_parquet(PROCESSED / "calfire_incidents.parquet")
    inc = inc[pd.to_numeric(inc.AcresBurned, errors="coerce") >= MIN_ACRES]
    inc = pd.DataFrame({"date": pd.to_datetime(inc.Started, utc=True).dt.tz_convert(TZ).dt.tz_localize(None).dt.normalize(),
                        "lat": inc.Latitude, "lon": inc.Longitude, "acres": pd.to_numeric(inc.AcresBurned),
                        "name": inc.Name, "source": "CAL FIRE incidents"})
    per = pd.read_parquet(PROCESSED / "calfire_perimeters.parquet")
    per = per[(pd.to_numeric(per.GIS_ACRES, errors="coerce") >= MIN_ACRES) & per.date.notna()]
    per = pd.DataFrame({"date": pd.to_datetime(per.date), "lat": per.lat, "lon": per.lon,
                        "acres": pd.to_numeric(per.GIS_ACRES), "name": per.FIRE_NAME, "source": "CAL FIRE perimeters"})
    recent = pd.concat([inc, per])
    recent = recent[recent.date >= "2021-01-01"].sort_values("source", ascending=False)  # incidents first (exact origin)
    keep = []
    for r in recent.itertuples():  # drop a perimeter that matches an incident within 2 days and 5 km
        if not any(abs((r.date - k.date).days) <= 2 and np.hypot(r.lat - k.lat, (r.lon - k.lon) * 0.84) < 0.045 for k in keep):
            keep.append(r)
    out = pd.concat([fpa, pd.DataFrame(keep).drop(columns="Index", errors="ignore")], ignore_index=True)
    return out.dropna(subset=["lat", "lon", "date"]).reset_index(drop=True)


def label_cells(g, s):
    pts = gpd.GeoDataFrame(s, geometry=gpd.points_from_xy(s.lon, s.lat), crs=4326).to_crs(3310)
    j = gpd.sjoin(pts, g[["cell", "geometry"]], predicate="within")
    return j[["cell", "date", "acres", "name", "source"]]


def fire_weather(hourly, last_rain=None):
    """Daily fire weather from an hourly frame (ts_utc index). last_rain: the last date with ≥0.1 in before this
    frame starts, so a short live window (10 past days) counts dry days the same way the full archive does."""
    d = weather_daily(hourly)
    h = hourly.copy()
    h["date"] = pd.to_datetime(h.index.tz_convert(TZ).date)
    d["rh_min"] = h.groupby("date").relative_humidity_2m.min()
    wet = d.precip >= 2.54  # 0.1 in
    since = (~wet).groupby(wet.cumsum()).cumsum()
    if last_rain is not None:  # days before the first wet day in the window continue the count from last_rain
        before_first = wet.cumsum() == 0
        since[before_first] = (d.index[before_first] - pd.Timestamp(last_rain)).days
    d["days_since_rain"] = since.clip(upper=365)
    return d[WEATHER]


def wet_dates(points, source=None, seed=None):
    """Dates with ≥0.1 in of observed rain per point over the last year: archive (seed) plus a recent hourly frame."""
    today = pd.Timestamp.now(tz=TZ).normalize().tz_localize(None)
    out = {p: set(v) for p, v in (seed or {}).items()}
    for p in points:
        h = source[p] if source else pd.read_parquet(PROCESSED / f"weather_{p}.parquet").set_index("ts_utc")
        daily = h.precipitation.groupby(pd.to_datetime(h.index.tz_convert(TZ).date)).sum()
        wet = daily[(daily >= 2.54) & (daily.index < today)]  # observed days only, not forecast rain
        out.setdefault(p, set()).update(f"{d:%Y-%m-%d}" for d in wet.index)
    cutoff = f"{today - pd.Timedelta(days=400):%Y-%m-%d}"
    return {p: sorted(d for d in v if d >= cutoff) for p, v in out.items()}


def last_rain_before(dates, start):
    """Latest wet date before `start`; if none in the last year, treat it as a year ago (the training cap)."""
    prior = [d for d in dates if pd.Timestamp(d) < start]
    return pd.Timestamp(prior[-1]) if prior else start - pd.Timedelta(days=365)


def weather_table(points, source=None, last_rain=None):
    frames = []
    for p in points:
        h = source[p] if source else pd.read_parquet(PROCESSED / f"weather_{p}.parquet").set_index("ts_utc")
        frames.append(fire_weather(h, (last_rain or {}).get(p)).assign(point_id=p))
    return pd.concat(frames).rename_axis("date").reset_index()


def training_table(neg_rate=0.01, seed=0):
    """All positive cell-days plus a random `neg_rate` sample of negatives (weight 1/neg_rate) from 2014 on."""
    g = grid()
    have = {p for p in g.point_id.unique() if (PROCESSED / f"weather_{p}.parquet").exists()}
    missing = set(g.point_id) - have
    if missing:
        raise RuntimeError(f"weather missing for {len(missing)} grid points: run make history SOURCES=weather")
    wx = weather_table(sorted(have))
    lab = label_cells(g, starts())
    days = pd.date_range("2014-01-15", wx.date.max())
    rng = np.random.default_rng(seed)
    n_neg = int(len(g) * len(days) * neg_rate)
    neg = pd.DataFrame({"cell": g.cell.to_numpy()[rng.integers(0, len(g), n_neg)],
                        "date": days[rng.integers(0, len(days), n_neg)]})
    pos = lab[lab.date >= days[0]][["cell", "date"]].drop_duplicates()
    neg = neg.merge(pos.assign(_p=1), on=["cell", "date"], how="left").query("_p.isna()").drop(columns="_p")
    rows = pd.concat([pos.assign(y=1, w=1.0), neg.assign(y=0, w=1 / neg_rate)], ignore_index=True)
    rows = rows.merge(g[["cell", "point_id", *STATIC]], on="cell").merge(wx, on=["point_id", "date"], how="inner")
    rows["month"] = rows.date.dt.month
    return rows, g, lab, wx
