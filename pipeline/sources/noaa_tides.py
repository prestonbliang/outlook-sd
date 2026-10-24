"""NOAA CO-OPS tide gauges: San Diego 9410170 and La Jolla 9410230. Station datum (STND), feet, UTC."""
import pandas as pd

from ._common import get, upsert

API = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
MDAPI = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations"
STATIONS = {"9410170": "San Diego", "9410230": "La Jolla"}


def _fetch(station, product, begin, end, interval=None):
    params = {"station": station, "product": product, "datum": "STND", "units": "english",
              "time_zone": "gmt", "format": "json", "begin_date": f"{begin:%Y%m%d}", "end_date": f"{end:%Y%m%d}",
              "application": "OutlookSD"}
    if interval:
        params["interval"] = interval
    js = get(f"noaa_{station}", API, params, ext="json").json()
    if "error" in js:
        msg = js["error"].get("message", "")
        if "No data was found" in msg:
            return pd.DataFrame({"ts_utc": pd.Series(dtype="datetime64[ns, UTC]"), "ft": pd.Series(dtype=float)})
        raise RuntimeError(f"noaa {station} {product} {begin:%Y%m%d}: {msg}")
    df = pd.DataFrame(js.get("predictions") or js.get("data"))
    df = df.rename(columns={"t": "ts_utc", "v": "ft"})
    df["ts_utc"] = pd.to_datetime(df.ts_utc).dt.tz_localize("UTC")
    df["ft"] = pd.to_numeric(df.ft, errors="coerce")
    return df[["ts_utc", "ft"]]


def _chunks(start, end, days):
    t = pd.Timestamp(start)
    while t <= pd.Timestamp(end):
        e = min(t + pd.Timedelta(days=days - 1), pd.Timestamp(end))
        yield t, e
        t = e + pd.Timedelta(days=1)


def hourly(station, start, end, observed_product="hourly_height"):
    """Hourly observed + predicted + residual. hourly_height (verified) is ≤1 yr/request; water_level ≤31 d."""
    step = 365 if observed_product == "hourly_height" else 31
    obs = pd.concat([_fetch(station, observed_product, a, b) for a, b in _chunks(start, end, step)])
    if observed_product == "hourly_height":
        # verified hourly heights lag by weeks; fill the recent tail with preliminary 6-min water_level
        last = obs.dropna().ts_utc.max() if obs.ft.notna().any() else pd.Timestamp(start, tz="UTC")
        if last < pd.Timestamp(end, tz="UTC"):
            wl = pd.concat([_fetch(station, "water_level", a, b)
                            for a, b in _chunks(last.tz_localize(None).normalize(), end, 31)])
            obs = pd.concat([obs.dropna(), wl[wl.ts_utc > last]])
    obs = obs[obs.ts_utc.dt.minute == 0]  # 6-min → on-the-hour values
    pred = pd.concat([_fetch(station, "predictions", a, b, "h") for a, b in _chunks(start, end, 365)])
    df = obs.rename(columns={"ft": "observed_ft"}).merge(pred.rename(columns={"ft": "predicted_ft"}), on="ts_utc", how="outer")
    df["residual_ft"] = df.observed_ft - df.predicted_ft
    df["station"], df["tz_source"] = station, "GMT"
    return df.sort_values("ts_utc").reset_index(drop=True)


def predictions(station, start, end):
    return pd.concat([_fetch(station, "predictions", a, b, "h") for a, b in _chunks(start, end, 365)])


def metadata(station):
    datums = get(f"noaa_{station}", f"{MDAPI}/{station}/datums.json", {"units": "english"}, ext="json").json()
    floods = get(f"noaa_{station}", f"{MDAPI}/{station}/floodlevels.json", ext="json").json()
    return {d["name"]: d["value"] for d in datums["datums"]}, floods


def fetch_history(start="1996-01-01", end=None):
    end = end or pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    for st in STATIONS:
        upsert(hourly(st, start, end), f"tides_{st}", ["ts_utc"])


def fetch_live():
    today = pd.Timestamp.utcnow().normalize().tz_localize(None)
    out = {}
    for st in STATIONS:
        obs = hourly(st, today - pd.Timedelta(days=3), today, observed_product="water_level")
        out[st] = upsert(obs.dropna(subset=["observed_ft"]), f"tides_{st}", ["ts_utc"])
    return out
