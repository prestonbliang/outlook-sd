"""Air: LightGBM quantile models (q50, q90) of daily AQI per monitor, days 0–3 ahead; PM2.5 and ozone separately.

Train ≤2023, early-stop on 2024, test 2025+. Baseline: persistence (yesterday's AQI). AirNow's official forecast is
compared on live days (historical AirNow forecasts are logged from the day the key is added).
"""
import lightgbm as lgb
import numpy as np
import pandas as pd

from models.common import block_bootstrap, save, split
from pipeline.features import air

PARAMS = dict(objective="quantile", learning_rate=0.03, num_leaves=31, min_data_in_leaf=100,
              feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, verbose=-1)
CATS = [(50, "good"), (100, "moderate"), (150, "usg"), (200, "unhealthy"), (300, "very_unhealthy"), (10_000, "hazardous")]


def category(a):
    return np.select([a <= lim for lim, _ in CATS], [c for _, c in CATS], "hazardous")


def fit(train, val, alpha):
    return lgb.train({**PARAMS, "alpha": alpha}, lgb.Dataset(train[air.FEATURES], train.aqi), 3000,
                     valid_sets=[lgb.Dataset(val[air.FEATURES], val.aqi)], callbacks=[lgb.early_stopping(150, verbose=False)])


def scores(t, col):
    obs_cat, pred_cat = category(t.aqi), category(t[col])
    usg_obs, usg_pred = t.aqi > 100, t[col] > 100
    return {"mae": float((t.aqi - t[col]).abs().mean()), "category_hit_rate": float((obs_cat == pred_cat).mean()),
            "usg_days": int(usg_obs.sum()), "usg_hits": int((usg_obs & usg_pred).sum()),
            "usg_hit_rate": float((usg_obs & usg_pred).sum() / max(usg_obs.sum(), 1)),
            "usg_false_alarms": int((~usg_obs & usg_pred).sum())}


def main():
    metrics, files = {}, {}
    for param in ["pm25", "ozone"]:
        d, st = air.training_table(param)
        train, val, test = split(d, "date", "train"), split(d, "date", "val"), split(d, "date", "test")
        print(f"{param}: train={len(train)} val={len(val)} test={len(test)} sites={d.site.nunique()}")
        m50, m90 = fit(train, val, 0.5), fit(train, val, 0.9)
        t = test.copy()
        t["q50"], t["q90"] = m50.predict(t[air.FEATURES]), m90.predict(t[air.FEATURES])
        t["persist"] = t.aqi_prev
        t["week"] = t.date.dt.to_period("W").astype(str)
        mae = lambda c: (lambda g: float((g.aqi - g[c]).abs().mean()))
        metrics[param] = {
            "period": {"train": "2014 → 2023", "val": "2024", "test": f"2025-01 → {test.date.max():%Y-%m-%d}"},
            "mae_ci": {c: block_bootstrap(t, "week", mae(c), n=300) for c in ["q50", "persist"]},
            "model": scores(t, "q50"), "model_high_end": scores(t, "q90"), "persistence": scores(t, "persist"),
            "by_lead": {int(k): scores(g, "q50")["mae"] for k, g in t.groupby("lead_k")},
            "persistence_by_lead": {int(k): scores(g, "persist")["mae"] for k, g in t.groupby("lead_k")},
        }
        metrics[param]["beats_baseline"] = metrics[param]["model"]["mae"] < metrics[param]["persistence"]["mae"]
        files[f"model_{param}_q50.txt"], files[f"model_{param}_q90.txt"] = m50, m90
        files[f"sites_{param}.json"] = st.reset_index().rename(columns={"site_id": "site"}).to_dict("records")
        files[f"site_categories_{param}.json"] = [str(c) for c in train.site.cat.categories]
        r = metrics[param]
        print(" MAE", {c: (round(v["value"], 2), [round(x, 2) for x in v["ci95"]]) for c, v in r["mae_ci"].items()})
        for k in ["model", "model_high_end", "persistence"]:
            print(f" {k}:", {a: (round(b, 3) if isinstance(b, float) else b) for a, b in r[k].items()})
        print(" by lead (model / persistence):", {k: (round(v, 1), round(r["persistence_by_lead"][k], 1)) for k, v in r["by_lead"].items()})
    metrics["inputs"] = "Scored with actual (ERA5) weather, an upper bound on live accuracy"
    metrics["beats_baseline"] = all(metrics[p]["beats_baseline"] for p in ["pm25", "ozone"])
    save("air", {**files, "feature_list.json": air.FEATURES, "metrics.json": metrics,
                 "thresholds.json": {"aqi_categories": CATS}})
    print("beats baseline:", metrics["beats_baseline"])


if __name__ == "__main__":
    main()
