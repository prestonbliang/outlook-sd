"""Hourly job: fetch_live → predict → log forecasts → score matured forecasts. Usage: python -m pipeline.run_all"""
import json
import traceback

import pandas as pd

from models.common import ART
from models.version import artifact_version
from pipeline import db, predict
from pipeline.features import air, fire, flood, heat, water
from pipeline.sources import (airnow, apcd, beachwatch, calfire, calheatscore, cdip, cool_zones, firms, geo, ibwc,
                              noaa_tides, nws, reports, sd_fire_ems)
from pipeline.sources._common import PROCESSED, ROOT, redact, write
from pipeline.storage import atomic_output

TZ = "America/Los_Angeles"


def newest(df, col):
    return None if df is None or not len(df) or col not in df else str(pd.to_datetime(df[col]).max())


def run_source(con, name, fn, time_col=None, every_hours=None):
    """Fetch one source; record success/failure and the newest data time. Returns the frame or None."""
    now = pd.Timestamp.now(tz="UTC")
    if every_hours:
        row = con.execute("SELECT last_success FROM source_status WHERE source=?", (name,)).fetchone()
        if row and row[0] and now - pd.Timestamp(row[0]) < pd.Timedelta(hours=every_hours):
            return None
    try:
        df = fn()
        db.set_status(con, name, str(now), success=str(now), newest=newest(df, time_col))
        return df
    except Exception as e:  # one failing source must not stop the run; the UI shows it as stale
        db.set_status(con, name, str(now), error=redact("".join(traceback.format_exception_only(e)).strip())[:500])
        print(f"[{name}] FAILED: {redact(str(e))[:300]}")
        return None


def fetch_all(con):
    zips = sorted({p["zip"] for p in json.loads((ROOT / "api" / "places.json").read_text())})
    run_source(con, "ibwc", lambda: ibwc.fetch_live()[1], "ts_utc")
    run_source(con, "noaa_tides", lambda: noaa_tides.fetch_live()[flood.STATION].dropna(subset=["observed_ft"]), "ts_utc")
    run_source(con, "cdip", cdip.fetch_live, "ts_utc")
    alerts = run_source(con, "nws", nws.fetch_live, "onset")
    if alerts is not None:
        write(alerts, "nws_alerts_live")
    run_source(con, "calheatscore", lambda: calheatscore.fetch_live(zips), "issued", every_hours=6)
    fires = run_source(con, "calfire", calfire.fetch_live, "Updated")
    if fires is not None:
        write(fires, "calfire_active")
    run_source(con, "airnow", lambda: airnow.fetch_live()[0], "ts_utc")
    run_source(con, "firms", firms.fetch_live, "ts_utc")
    run_source(con, "sd_fire_ems", sd_fire_ems.fetch_live, "date", every_hours=24)
    run_source(con, "reports", reports.fetch_live, "day")
    run_source(con, "apcd", apcd.fetch_live, "date", every_hours=12)
    run_source(con, "cool_zones", cool_zones.fetch_live, every_hours=24)
    run_source(con, "calfire_year", lambda: calfire.update_incidents(pd.Timestamp.now(tz=TZ).year), "StartedDateOnly",
               every_hours=24)
    run_source(con, "beachwatch", lambda: (beachwatch.fetch_history(),
                                           pd.read_parquet(PROCESSED / "beach_results.parquet"))[1],
               "date", every_hours=24)


def weather_points():
    points = {flood.POINT}
    points.update(p["point_id"] for p in json.loads((ROOT / "api" / "places.json").read_text()) if p.get("point_id"))
    # Include Air's inland monitor points even when they aren't near a named place.
    for tile, files in {"water": ["stations.json"], "air": ["sites_pm25.json", "sites_ozone.json"]}.items():
        for name in files:
            path = ART / tile / name
            if path.exists():
                points.update(s["point_id"] for s in json.loads(path.read_text()) if s.get("point_id"))
    if (PROCESSED / "zcta_sd.parquet").exists():
        points.update(heat.zip_points().point_id)
    if (PROCESSED / "fire_grid.parquet").exists() or all((PROCESSED / p).exists() for p in
            ["county.parquet", "fhsz_sd.parquet", "calfire_perimeters.parquet", "roads_sd.parquet"]):
        points.update(fire.grid().point_id)
    return sorted(points)


def model_version(tile):
    return artifact_version(ART / tile)


def forecast_all(con, run_ts):
    now = pd.Timestamp.now(tz="UTC")
    wx = run_source(con, "openmeteo", lambda: predict.forecast_hourly(weather_points()), time_col=None)
    if wx is None:
        return
    try:
        save_weather_series(wx)
    except Exception as e:
        print(f"[weather series] FAILED: {redact(str(e))[:300]}")
    places = json.loads((ROOT / "api" / "places.json").read_text())
    tiles = [("flood", predict.predict_flood), ("water", predict.predict_water), ("heat", predict.predict_heat),
             ("fire", lambda n, w: predict.predict_fire(n, w, places)), ("air", predict.predict_air)]
    for tile, fn in tiles:
        if not (ART / tile / "metrics.json").exists():
            continue
        if tile == "air" and not (PROCESSED / "airnow_obs.parquet").exists():
            continue  # live Air needs AirNow observations (AIRNOW_API_KEY)
        try:
            rows, detail = fn(now, wx)
            db.log_forecasts(con, run_ts, tile, rows, model_version(tile))
            if tile == "flood":  # hourly curve for the detail chart
                write(detail[["target", "tide_pred", "lvl50", "lvl90"]], "flood_forecast_hourly")
            if tile == "fire":
                for date, day in detail.groupby("date"):
                    cells = fire.grid().merge(day[["cell", "p", "level"]], on="cell").to_crs(4326)
                    with atomic_output(PROCESSED / f"map_fire_cells-{date:%Y-%m-%d}.geojson") as path:
                        cells[["cell", "p", "level", "geometry"]].to_file(path, driver="GeoJSON")
            print(f"{tile}: {len(rows)} forecasts")
        except Exception as e:
            print(f"[predict {tile}] FAILED: {redact(str(e))[:300]}")
            traceback.print_exc()


def save_weather_series(wx):
    """Daily high/low/rain per grid point (last 10 days + forecast) for the Heat and Water detail charts."""
    frames = []
    for p, h in wx.items():
        d = heat.daily_weather(h)
        d["rain_mm"] = water.rain_daily(p, source=h)
        frames.append(d.assign(point_id=p))
    write(pd.concat(frames).rename_axis("date").reset_index(), "weather_daily_live")


def log_place_levels(con, run_ts):
    """What each place's tiles said, per day — the reference that community reports are checked against."""
    from api.main import PLACES, outlook_for  # same assembly the app shows
    rows = []
    for p in PLACES:
        for t in outlook_for(p)["tiles"]:
            rows += [(run_ts, p["id"], t["tile"], d["date"], d["level"]) for d in t["days"][:1]]  # day 0 only
    con.executemany("INSERT OR REPLACE INTO place_levels VALUES (?,?,?,?,?)", rows)
    con.commit()


def write_maps(con):
    """GeoJSON layers for the map: Heat by ZIP (model ZIPs, CalHeatScore elsewhere), Flood coastal outlines."""
    import geopandas as gpd
    today = str(pd.Timestamp.now(tz=TZ).date())
    z = geo.zcta().assign(geometry=lambda g: g.simplify(0.0005))
    h = pd.read_sql("SELECT unit_id AS zip, value, level, extra_json FROM forecasts WHERE tile='heat' AND target_date=? "
                    "AND run_ts=(SELECT MAX(run_ts) FROM forecasts WHERE tile='heat')", con, params=(today,))
    chs_path = PROCESSED / "calheatscore_log.parquet"
    chs = pd.read_parquet(chs_path) if chs_path.exists() else pd.DataFrame()
    chs = chs[(chs.issued == chs.issued.max()) & (chs.target_date.astype(str) == today)].set_index("zip").chs \
        if len(chs) else pd.Series(dtype=float)
    z = z.merge(h, on="zip", how="left")
    z["source"] = z.value.notna().map({True: "outlook", False: "calheatscore"})
    z["chs"] = z.zip.map(chs)
    with atomic_output(PROCESSED / "map_heat.geojson") as path:
        z[["zip", "value", "level", "source", "chs", "geometry"]].to_file(path, driver="GeoJSON")
    f = pd.read_sql("SELECT value, level FROM forecasts WHERE tile='flood' AND target_date=? "
                    "AND run_ts=(SELECT MAX(run_ts) FROM forecasts WHERE tile='flood')", con, params=(today,))
    if not (PROCESSED / "coastal_places.parquet").exists():
        return
    cp = gpd.read_parquet(PROCESSED / "coastal_places.parquet")
    if len(f):
        cp["level"], cp["peak_ft_mllw"] = f.level.iloc[0], round(f.value.iloc[0] - 3.79, 2)
    with atomic_output(PROCESSED / "map_flood.geojson") as path:
        cp.to_file(path, driver="GeoJSON")


def observed(tile):
    """Observed outcome per (unit_id, local date) once it has arrived."""
    if tile == "flood":
        t = flood.load_tides().observed_ft.dropna()
        d = t.groupby(t.index.tz_convert(TZ).date).max()
        d = d[d.index < pd.Timestamp.now(tz=TZ).date()]  # Never discard a completed day when today's observations are missing.
        return {(flood.STATION, str(k)): float(v) for k, v in d.items()}
    if tile == "water":
        lab, _ = water.labels()
        return {(s, f"{dt:%Y-%m-%d}"): float(r) for s, dt, r in zip(lab.station, lab.date, lab.ratio)}
    if tile == "heat":
        e = pd.read_parquet(PROCESSED / "ems_daily_zip.parquet")
        return {(z, str(dt)): float(c) for z, dt, c in zip(e.zip, e.date, e.calls)}
    if tile == "air":
        o = pd.read_parquet(PROCESSED / "airnow_obs.parquet") if (PROCESSED / "airnow_obs.parquet").exists() else None
        if o is None:
            return {}
        d = air.daily_aqi_from_hourly(o.dropna(subset=["site", "parameter", "conc"])[["site", "parameter", "ts_utc", "conc"]])
        d = d[d.date < pd.Timestamp.now(tz=TZ).normalize().tz_localize(None)]  # complete days only
        return {(f"{p}:{s}", f"{dt:%Y-%m-%d}"): float(a) for p, s, dt, a in zip(d.parameter, d.site, d.date, d.aqi)}
    if tile == "fire":  # county-wide count of new fires that reached the size threshold, for past days
        s = fire.starts()
        s = s[s.date < pd.Timestamp.now(tz=TZ).normalize().tz_localize(None)]
        counts = s.groupby(s.date.dt.strftime("%Y-%m-%d")).size()
        days = pd.date_range("2026-10-01", pd.Timestamp.now(tz=TZ).normalize().tz_localize(None) - pd.Timedelta(days=1))
        return {("county", f"{d:%Y-%m-%d}"): float(counts.get(f"{d:%Y-%m-%d}", 0)) for d in days}
    return {}


def score_all(con):
    """Write scores for forecasts whose target date has an observed outcome. Hit = agreement on the warning event:
    flood ≥ minor flood level; water ≥ 50% vs sample above standard; heat = expected vs observed calls within 20%."""
    thr = json.loads((ART / "flood" / "thresholds.json").read_text())
    pending = pd.read_sql("SELECT f.id, f.tile, f.unit_id, f.target_date, f.value, f.extra_json FROM forecasts f "
                          "LEFT JOIN scores s ON s.forecast_id = f.id WHERE s.forecast_id IS NULL", con)
    now, rows = str(pd.Timestamp.now(tz="UTC")), []
    for tile, g in pending.groupby("tile"):
        try:
            obs = observed(tile)
        except (FileNotFoundError, KeyError) as e:
            print(f"[score {tile}] Waiting for source data: {redact(str(e))[:200]}")
            continue
        for r in g.itertuples():
            o = obs.get((r.unit_id, r.target_date))
            if o is None:
                continue
            if tile == "flood":
                lvl = predict.level_of(o, thr["levels"])
                hit = (r.value >= thr["minor"]) == (o >= thr["minor"])
            elif tile == "air":
                lvl = predict.aqi_category(o)
                hit = lvl == predict.aqi_category(r.value)
            elif tile == "fire":
                if r.unit_id != "county":
                    continue
                lvl, hit = None, None  # county expected count vs observed count; no single yes/no hit
            elif tile == "water":
                lvl, hit = ("exceeds" if o > 1 else "meets"), (r.value >= 0.5) == (o > 1)
            else:
                exp = json.loads(r.extra_json)["expected_calls"]
                lvl, hit = None, abs(o - exp) <= 0.2 * max(exp, 1)
            rows.append((r.id, o, lvl, None if hit is None else int(hit), now))
    con.executemany("INSERT OR REPLACE INTO scores VALUES (?,?,?,?,?)", rows)
    con.commit()
    print(f"scored {len(rows)} forecasts")


def main():
    con = db.connect()
    run_ts = pd.Timestamp.now(tz="UTC").isoformat()
    fetch_all(con)
    forecast_all(con, run_ts)
    if (PROCESSED / "zcta_sd.parquet").exists():
        try:
            write_maps(con)
        except Exception as e:
            print(f"[map] FAILED: {redact(str(e))[:300]}")
    else:
        print("[map] ZIP outlines missing. Run make history SOURCES=geo to build them.")
    log_place_levels(con, run_ts)
    score_all(con)
    con.close()


if __name__ == "__main__":
    main()
