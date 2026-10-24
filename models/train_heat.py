"""Heat: LightGBM Poisson model of daily Fire-Rescue calls per ZIP; excess = prediction − same model at normal temps.

Train ≤2023, early-stop on 2024, test 2025-01 → last EMS date. Baselines: same day last week; the model with
temperatures at normal (no heat signal). CalHeatScore has no history, so it is compared on live days only.
"""
import lightgbm as lgb
import pandas as pd

from models.common import block_bootstrap, save, split
from pipeline.features import heat
from pipeline.sources._common import PROCESSED

MONOTONE = {"tmax", "tmin", "heat_index_max", "tmax_lag1", "hot_streak"}  # hotter never means fewer calls
PARAMS = dict(objective="poisson", learning_rate=0.03, num_leaves=63, min_data_in_leaf=100,
              feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, verbose=-1,
              monotone_constraints=[int(f in MONOTONE) for f in heat.FEATURES])


def normals(train):
    """Monthly normal of each heat feature per grid point (training years only)."""
    n = train.groupby(["point_id", "month"])[heat.HEAT].mean()
    n["hot_streak"] = 0.0
    return n


def at_normal(d, norm):
    x = d.copy()
    nn = norm.reindex(pd.MultiIndex.from_arrays([x.point_id, x.month])).to_numpy()
    x[heat.HEAT] = nn
    return x


def main():
    d, hot_thr = heat.training_table()
    train, val, test = split(d, "date", "train"), split(d, "date", "val"), split(d, "date", "test")
    print(f"rows train={len(train)} val={len(val)} test={len(test)}; test ends {test.date.max():%Y-%m-%d}")
    m = lgb.train(PARAMS, lgb.Dataset(train[heat.FEATURES], train.calls), 4000,
                  valid_sets=[lgb.Dataset(val[heat.FEATURES], val.calls)],
                  callbacks=[lgb.early_stopping(200, verbose=False)])
    norm = normals(train)
    p95 = train.groupby("point_id").tmax.quantile(0.95)

    t = test.copy()
    t["pred"] = m.predict(t[heat.FEATURES])
    t["normal"] = m.predict(at_normal(t, norm)[heat.FEATURES])
    last_week = d.set_index(["date", "zip"]).calls
    t["last_week"] = last_week.reindex(pd.MultiIndex.from_arrays([t.date - pd.Timedelta(days=7), t.zip])).to_numpy()
    t["hot"] = t.tmax > t.point_id.map(p95)
    t["week"] = t.date.dt.to_period("W").astype(str)
    t = t.dropna(subset=["last_week"])

    mae = lambda c: (lambda x: float((x.calls - x[c]).abs().mean()))
    cols = ["pred", "normal", "last_week"]
    city = t.groupby("date").agg(calls=("calls", "sum"), pred=("pred", "sum"), normal=("normal", "sum"),
                                 last_week=("last_week", "sum"), hot=("hot", "mean")).reset_index()
    city["week"] = city.date.dt.to_period("W").astype(str)
    hot_city = city[city.hot >= 0.5]  # at least half the ZIPs above their 95th-percentile high
    ex = lambda c: (lambda x: float(((x.calls - x.normal) - (x[c] - x.normal)).abs().mean()))
    metrics = {
        "zip_day_mae": {c: block_bootstrap(t, "week", mae(c), n=300) for c in cols},
        "zip_day_mae_hot_days": {c: mae(c)(t[t.hot]) for c in cols},
        "citywide_daily_mae": {c: block_bootstrap(city, "week", mae(c), n=300) for c in cols},
        "citywide_hot_days": {"n_days": int(len(hot_city)),
                              "excess_error": {c: ex(c)(hot_city) for c in ["pred", "last_week"]},
                              "mean_observed_excess": float((hot_city.calls - hot_city.normal).mean()),
                              "mean_predicted_excess": float((hot_city.pred - hot_city.normal).mean())},
        "period": {"train": "2016-09 → 2023-12", "val": "2024", "test": f"2025-01 → {test.date.max():%Y-%m-%d}"},
        "inputs": "Scored with actual (ERA5) weather, an upper bound on live accuracy",
    }
    metrics["beats_baseline"] = bool(metrics["zip_day_mae"]["pred"]["value"]
                                     < min(metrics["zip_day_mae"][c]["value"] for c in ["normal", "last_week"]))

    # neighborhood heat sensitivity: % extra calls on hot days, train+val years
    tv = pd.concat([train, val]).copy()
    tv["pred"], tv["normal"] = m.predict(tv[heat.FEATURES]), m.predict(at_normal(tv, norm)[heat.FEATURES])
    tv_hot = tv[tv.tmax > tv.point_id.map(p95)]
    sens = (tv_hot.groupby("zip").pred.sum() / tv_hot.groupby("zip").normal.sum() - 1).sort_values(ascending=False)
    metrics["heat_sensitivity_pct"] = (sens * 100).round(1).to_dict()

    # excess-per-10k thresholds for levels (needs ACS population)
    acs_path = PROCESSED / "acs_zcta.parquet"
    thresholds = {"hot_tmax_p95_c": p95.round(2).to_dict(), "streak_tmax_p90_c": hot_thr}
    if acs_path.exists():
        pop = pd.read_parquet(acs_path).set_index("zip").population
        p = tv.zip.map(pop)
        per10k = ((tv.pred - tv.normal) / p * 1e4)[p >= 1000]  # skip ZIPs with very few residents
        q = per10k.quantile([0.75, 0.90, 0.97]).tolist()
        thresholds["excess_per_10k"] = {"moderate": q[0], "high": q[1], "very_high": q[2]}
    else:
        thresholds["excess_per_10k"] = None
        print("ACS population missing → level thresholds not set (run make history SOURCES=acs)")

    # Oct 3, 2026 heat (EMS for that date is not published yet): model forecast vs model normal, citywide
    replay = {"name": "Oct 3, 2026 heat", "note": "City EMS file ends " + f"{d.date.max():%Y-%m-%d}" +
              "; observed calls for this week are not yet published. KPBS reported 925 calls in 24 h (42% above normal)."}
    metrics["replays"] = [replay]
    metrics["hot_test_days"] = hot_city.sort_values("calls", ascending=False).head(10)[
        ["date", "calls", "pred", "normal", "last_week"]].round(1).astype({"date": str}).to_dict("records")
    save("heat", {"model.txt": m, "feature_list.json": heat.FEATURES, "thresholds.json": thresholds,
                  "metrics.json": metrics,
                  "normals.json": {f"{p}|{mo}": r for (p, mo), r in norm.round(3).to_dict("index").items()}})

    fmt = lambda v: (round(v["value"], 2), [round(x, 2) for x in v["ci95"]])
    print("ZIP-day MAE:", {c: fmt(v) for c, v in metrics["zip_day_mae"].items()})
    print("ZIP-day MAE hot days:", {c: round(v, 2) for c, v in metrics["zip_day_mae_hot_days"].items()})
    print("citywide daily MAE:", {c: fmt(v) for c, v in metrics["citywide_daily_mae"].items()})
    print("citywide hot days:", metrics["citywide_hot_days"])
    print("top heat-sensitive ZIPs (% extra calls on hot days):", list(metrics["heat_sensitivity_pct"].items())[:8])
    print(pd.DataFrame(metrics["hot_test_days"]).to_string(index=False))
    print("beats baseline:", metrics["beats_baseline"])


if __name__ == "__main__":
    main()
