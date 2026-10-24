"""Flood: LightGBM quantile models (q50, q90) of the hourly tide residual, 1–72 h ahead, at NOAA 9410170.

The models predict the change from the latest observed residual (trees cannot extrapolate, so an absolute
target shrinks storm surges toward the training range); residual = latest residual + predicted change.
Peak level = NOAA tide prediction + predicted residual. Train ≤2023, early-stop on 2024, test 2025–26.
Baselines: residual = 0 (tide only) and persistence of the latest residual.
"""
import lightgbm as lgb
import numpy as np
import pandas as pd

from models.common import block_bootstrap, save, split
from pipeline.features import flood
from pipeline.sources._common import PROCESSED

MINOR, MODERATE, MAJOR = 11.38, 12.31, 13.58  # NOS flood levels, ft STND (floodlevels.json)
MHHW = 9.52
LEVELS = {"low": [None, MHHW + 1.0], "moderate": [MHHW + 1.0, MINOR], "high": [MINOR, MODERATE],
          "very_high": [MODERATE, None]}
PARAMS = dict(objective="quantile", learning_rate=0.05, num_leaves=31, min_data_in_leaf=200,
              feature_fraction=0.9, bagging_fraction=0.8, bagging_freq=1, verbose=-1)


def fit(train, val, alpha):
    dtr = lgb.Dataset(train[flood.FEATURES], train.residual - train.resid_now)
    dva = lgb.Dataset(val[flood.FEATURES], val.residual - val.resid_now)
    return lgb.train({**PARAMS, "alpha": alpha}, dtr, 3000, valid_sets=[dva],
                     callbacks=[lgb.early_stopping(100, verbose=False)])


def daily_peaks(d, cols):
    """Per (issue, local day k = 0..3): max over the target hours of that local date. 12z issues only (~5 am PT)."""
    d = d[d.issue.dt.hour == 12].copy()
    local = d.target.dt.tz_convert("America/Los_Angeles").dt.date
    d["day"] = (pd.to_datetime(local) - pd.to_datetime(d.issue.dt.tz_convert("America/Los_Angeles").dt.date)).dt.days
    d = d[d.day.between(0, 3)]
    return d.groupby(["issue", "day"])[cols].max().reset_index()


def event_scores(peaks, pred_col, obs_col="obs_peak", thr=MINOR):
    p, o = peaks[pred_col] >= thr, peaks[obs_col] >= thr
    hits, misses, fa = int((p & o).sum()), int((~p & o).sum()), int((p & ~o).sum())
    return {"hits": hits, "misses": misses, "false_alarms": fa, "observed_events": int(o.sum()),
            "hit_rate": hits / max(hits + misses, 1), "false_alarm_ratio": fa / max(hits + fa, 1)}


def predict(model, d):
    return d.resid_now.to_numpy() + model.predict(d[flood.FEATURES])


def evaluate(test, m50, m90):
    t = test.copy()
    t["q50"], t["q90"] = predict(m50, t), predict(m90, t)
    t["week"] = t.issue.dt.tz_convert(None).dt.to_period("W").astype(str)
    rmse = lambda col: (lambda d: float(np.sqrt(np.mean((d.residual - d[col]) ** 2))))
    t["zero"] = 0.0
    t["persist"] = t.resid_now
    out = {"residual_rmse_ft": {c: block_bootstrap(t, "week", rmse(c), n=300) for c in ["q50", "zero", "persist"]},
           "residual_rmse_by_day": {}, "q90_coverage": float((t.residual <= t.q90).mean())}
    t["lead_day"] = (t.lead_h - 1) // 24 + 1
    for k, g in t.groupby("lead_day"):
        out["residual_rmse_by_day"][f"day{k}"] = {c: rmse(c)(g) for c in ["q50", "zero", "persist"]}
    for c in ["q50", "q90", "zero", "persist"]:
        t[f"lvl_{c}"] = t.tide_pred + t[c]
    peaks = daily_peaks(t, ["observed", *[f"lvl_{c}" for c in ["q50", "q90", "zero", "persist"]]])
    peaks = peaks.rename(columns={"observed": "obs_peak"})
    out["minor_flood_days"] = {c: event_scores(peaks, f"lvl_{c}") for c in ["q50", "q90", "zero", "persist"]}
    out["peak_mae_ft"] = {c: float((peaks[f"lvl_{c}"] - peaks.obs_peak).abs().mean()) for c in ["q50", "zero", "persist"]}
    return out, t


def hindcast(test, m50, m90):
    """Re-score the test period using archived forecasts (Open-Meteo Previous Runs) instead of ERA5:
    leads of 1–24 h use the run from 1 day before, 25–48 h from 2 days before, 49–72 h from 3 days before."""
    path = PROCESSED / f"previous_runs_{flood.POINT}.parquet"
    if not path.exists():
        return None
    prev = pd.read_parquet(path).set_index("ts_utc")
    tides, waves, era5 = flood.load_tides(), flood.load_waves(), flood.load_weather()
    issues = pd.DatetimeIndex(sorted(test.issue.unique()))
    issues = issues[issues >= prev.index.min() + pd.Timedelta(days=3)]
    parts = []
    for day in (1, 2, 3):
        w = prev[[c for c in prev.columns if c.endswith(f"_previous_day{day}")]]
        w = flood.add_wind_components(w.rename(columns=lambda c: c.replace(f"_previous_day{day}", "")))
        rows = flood.build(issues, tides, w, waves, era5.surface_pressure)  # pressure now = observed (ERA5) at issue
        parts.append(rows[(rows.lead_h - 1) // 24 + 1 == day])
    h = pd.concat(parts).dropna(subset=["residual", "pressure"])
    metrics, _ = evaluate(h, m50, m90)
    metrics["n_issues"] = int(h.issue.nunique())
    return metrics


def replay(t_all, issue, m50, m90, name):
    d = t_all[t_all.issue == pd.Timestamp(issue, tz="UTC")].copy()
    d["lvl_q50"] = d.tide_pred + predict(m50, d)
    d["lvl_q90"] = d.tide_pred + predict(m90, d)
    d["lvl_tide"] = d.tide_pred
    p = daily_peaks(d, ["observed", "lvl_q50", "lvl_q90", "lvl_tide"])
    p["date"] = (pd.to_datetime(p.issue.dt.tz_convert("America/Los_Angeles").dt.date)
                 + pd.to_timedelta(p.day, unit="D")).dt.date.astype(str)
    return {"name": name, "issued": str(issue),
            "days": p[["date", "observed", "lvl_q50", "lvl_q90", "lvl_tide"]].round(2).to_dict("records")}


def main():
    d = flood.training_table()
    train, val, test = split(d, "issue", "train"), split(d, "issue", "val"), split(d, "issue", "test")
    print(f"rows train={len(train)} val={len(val)} test={len(test)}")
    m50, m90 = fit(train, val, 0.5), fit(train, val, 0.9)
    metrics, _ = evaluate(test, m50, m90)
    metrics["period"] = {"train": "2014-01 → 2023-12", "val": "2024", "test": f"2025-01 → {test.issue.max():%Y-%m-%d}"}
    metrics["inputs"] = "Scored with actual (ERA5) weather, an upper bound on live accuracy"
    metrics["replays"] = [replay(d, "2026-10-09 12:00", m50, m90, "Tropical Storm Rachel (Oct 10–12, 2026)"),
                          replay(d, "2024-01-20 12:00", m50, m90, "January 2024 storm (validation year)")]
    metrics["hindcast"] = hindcast(test, m50, m90)
    if metrics["hindcast"]:
        hc = metrics["hindcast"]
        print("HINDCAST (archived forecasts):", {k: round(v["value"], 3) for k, v in hc["residual_rmse_ft"].items()},
              {k: (v["hits"], v["observed_events"], v["false_alarms"]) for k, v in hc["minor_flood_days"].items()})
    beats = metrics["residual_rmse_ft"]["q50"]["value"] < min(metrics["residual_rmse_ft"][c]["value"] for c in ["zero", "persist"])
    metrics["beats_baseline"] = bool(beats)
    save("flood", {"model_q50.txt": m50, "model_q90.txt": m90, "feature_list.json": flood.FEATURES,
                   "thresholds.json": {"units": "ft STND (NOAA 9410170)", "minor": MINOR, "moderate": MODERATE,
                                       "major": MAJOR, "mhhw": MHHW, "navd88_offset": 4.22, "levels": LEVELS},
                   "metrics.json": metrics})
    r = metrics["residual_rmse_ft"]
    print("residual RMSE ft:", {k: (round(v["value"], 3), [round(x, 3) for x in v["ci95"]]) for k, v in r.items()})
    print("by day:", {k: {c: round(x, 3) for c, x in v.items()} for k, v in metrics["residual_rmse_by_day"].items()})
    print("q90 coverage:", round(metrics["q90_coverage"], 3))
    for c, s in metrics["minor_flood_days"].items():
        print(f"minor-flood days [{c}]:", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.items()})
    print("peak MAE ft:", {k: round(v, 3) for k, v in metrics["peak_mae_ft"].items()})
    for rp in metrics["replays"]:
        print(rp["name"]); print(pd.DataFrame(rp["days"]).to_string(index=False))
    print("beats baseline:", beats)


if __name__ == "__main__":
    main()
