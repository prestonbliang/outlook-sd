"""Heat features: one row per ZIP × local date. Target = City of San Diego Fire-Rescue calls that day.

EMS data lags ~2 months, so recent call counts are NOT features; the call level comes from a 365-day mean that
ends 90 days before the target date (available at forecast time). Weather = the ZIP's ERA5 grid point, aggregated
to local (America/Los_Angeles) days.
"""
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

from pipeline.sources import geo, openmeteo
from pipeline.sources._common import PROCESSED

TZ = "America/Los_Angeles"
MIN_CALLS_PER_DAY = 1.0  # ZIPs below this are mostly mutual-aid calls outside the city
HEAT = ["tmax", "tmin", "heat_index_max", "rh_mean", "tmax_lag1", "hot_streak"]
FEATURES = ["zip_code", "dow", "month", "holiday", "level_365d", *HEAT]


def heat_index_f(t_c, rh):
    """NWS heat index (Rothfusz regression, °F); below ~80 °F the simple Steadman form is used."""
    t = t_c * 9 / 5 + 32
    simple = 0.5 * (t + 61 + (t - 68) * 1.2 + rh * 0.094)
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 6.83783e-3 * t ** 2
          - 5.481717e-2 * rh ** 2 + 1.22874e-3 * t ** 2 * rh + 8.5282e-4 * t * rh ** 2 - 1.99e-6 * t ** 2 * rh ** 2)
    return np.where((simple + t) / 2 < 80, simple, hi)


def zip_points():
    z = geo.zcta()
    c = z.to_crs(3310).centroid.to_crs(4326)
    z["point_id"] = openmeteo.grid_id(c.y, c.x)[0]
    return z[["zip", "point_id"]]


def daily_weather(hourly):
    """hourly: ts_utc index, temperature_2m (°C), relative_humidity_2m — one grid point."""
    h = hourly.copy()
    h["date"] = h.index.tz_convert(TZ).date
    h["hi"] = heat_index_f(h.temperature_2m, h.relative_humidity_2m)
    d = h.groupby("date").agg(tmax=("temperature_2m", "max"), tmin=("temperature_2m", "min"),
                              heat_index_max=("hi", "max"), rh_mean=("relative_humidity_2m", "mean"),
                              n=("temperature_2m", "size"))
    d = d[d.n >= 20].drop(columns="n")
    d.index = pd.to_datetime(d.index)
    d["tmax_lag1"] = d.tmax.shift(1)
    return d


def add_streak(d, hot_thr):
    hot = d.tmax > hot_thr
    d["hot_streak"] = hot.groupby((~hot).cumsum()).cumsum()
    return d


def weather_by_point(points, hot_thr=None, source=None):
    """source: optional {point_id: hourly frame} (e.g. forecast); default = ERA5 archive parquet files."""
    out, thr = [], {}
    for p in points:
        hourly = source[p] if source else pd.read_parquet(PROCESSED / f"weather_{p}.parquet").set_index("ts_utc")
        d = daily_weather(hourly)
        thr[p] = hot_thr[p] if hot_thr else float(d.loc[:"2023-12-31", "tmax"].quantile(0.90))
        out.append(add_streak(d, thr[p]).assign(point_id=p))
    return pd.concat(out).rename_axis("date").reset_index(), thr


def call_level(ems, until=None):
    """Mean daily calls per ZIP over the 365 days ending 90 days before each date (forecast-time safe).
    `until` extends the index past the last EMS date so future target dates get a level too."""
    e = ems.pivot_table(index="date", columns="zip", values="calls", fill_value=0).asfreq("D", fill_value=0)
    lvl = e.rolling(365, min_periods=180).mean()
    if until is not None:
        lvl = lvl.reindex(pd.date_range(lvl.index.min(), until, name="date"))
    lvl = lvl.shift(90)
    return lvl.stack().rename("level_365d").reset_index()


def calendar(df):
    hol = USFederalHolidayCalendar().holidays(df.date.min(), df.date.max() + pd.Timedelta(days=400))
    df["dow"], df["month"] = df.date.dt.dayofweek, df.date.dt.month
    df["holiday"] = df.date.isin(hol).astype(int)
    return df


def training_table():
    ems = pd.read_parquet(PROCESSED / "ems_daily_zip.parquet")
    ems["date"] = pd.to_datetime(ems.date)
    span = (ems.date.max() - ems.date.min()).days + 1
    keep = ems.groupby("zip").calls.sum().div(span).loc[lambda s: s >= MIN_CALLS_PER_DAY].index
    zp = zip_points()
    zp = zp[zp.zip.isin(keep)]
    # every ZIP-day in range (a day with no calls is a real zero)
    grid = pd.MultiIndex.from_product([pd.date_range(ems.date.min(), ems.date.max()), zp.zip], names=["date", "zip"])
    df = ems.set_index(["date", "zip"]).reindex(grid).fillna({"calls": 0, "calls_medical": 0}).reset_index()
    df = df.merge(zp, on="zip").merge(call_level(ems), on=["date", "zip"], how="left")
    wx, thr = weather_by_point(zp.point_id.unique())
    df = calendar(df.merge(wx, on=["date", "point_id"], how="inner"))
    df["zip_code"] = df.zip.astype("category")
    return df.dropna(subset=["level_365d", "tmax_lag1"]), thr
