"""Water: LightGBM classifier P(enterococcus > state standard) per station-day, days 0–3 ahead; isotonic calibration.

Split: train ≤2023 / val 2024 / test 2025–26 when border-flow history covers those years; otherwise a provisional
split on the years that have flow (flagged in metrics.json). Baselines: persistence (last sample before issue)
and the rain-only rule (closed if > 0.1 in of rain in the 72 h before the sample day).
"""
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, precision_recall_curve, roc_auc_score

from models.common import block_bootstrap, save
from pipeline.features import water

PARAMS = dict(objective="binary", learning_rate=0.03, num_leaves=31, min_data_in_leaf=100,
              feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, verbose=-1)
LEVELS = {"low": [None, 0.2], "moderate": [0.2, 0.5], "high": [0.5, 0.8], "very_high": [0.8, None]}
RAIN_RULE_MM = 2.54  # 0.1 in


def choose_split(d):
    if d.date.max() >= pd.Timestamp("2025-06-01"):
        return {"train": (None, "2023-12-31"), "val": ("2024-01-01", "2024-12-31"), "test": ("2025-01-01", None)}, False
    return {"train": (None, "2019-12-31"), "val": ("2020-01-01", "2020-12-31"), "test": ("2021-01-01", None)}, True


def take(d, lo, hi):
    m = pd.Series(True, index=d.index)
    if lo:
        m &= d.date >= lo
    if hi:
        m &= d.date <= hi
    return d[m]


def add_baselines(d, lab):
    """Persistence: ratio/exceed of the station's last sample strictly before the issue date."""
    last = lab.sort_values("date").rename(columns={"date": "last_date", "exceed": "last_exceed", "ratio": "last_ratio"})
    last["station"] = last.station.astype(str)
    last["last_date"] = last.last_date.astype("datetime64[ns]")
    x = d.assign(station_s=d.station.astype(str)).sort_values("issue")
    x["issue_m1"] = (x.issue - pd.Timedelta(days=1)).astype("datetime64[ns]")
    x = pd.merge_asof(x, last, left_on="issue_m1", right_on="last_date", left_by="station_s", right_by="station",
                      suffixes=("", "_l"), allow_exact_matches=True)
    x["rain_rule"] = x.rain_72h + x.rain_fcst  # mm in the window before/through the sample day
    return x.drop(columns=["station_l", "issue_m1"]).sort_index()


def recall_at_precision(y, s, p_min=0.8):
    p, r, _ = precision_recall_curve(y, s)
    ok = r[p >= p_min]
    return float(ok.max()) if len(ok) else 0.0


def scores(g, col):
    y = g.exceed.astype(int)
    s = g[col].fillna(0).astype(float)
    out = {"n": int(len(g)), "positives": int(y.sum())}
    if y.nunique() < 2:
        return out
    out["auc"] = float(roc_auc_score(y, s))
    out["recall_at_80pct_precision"] = recall_at_precision(y, s)
    if col == "prob":
        out["brier"] = float(brier_score_loss(y, s))
    flagged = s >= (0.5 if col == "prob" else (1.0 if col == "last_ratio" else RAIN_RULE_MM))
    out["hit_rate"] = float((flagged & (y == 1)).sum() / max(y.sum(), 1))
    out["false_alarm_ratio"] = float((flagged & (y == 0)).sum() / max(flagged.sum(), 1))
    return out


def main():
    d, st = water.training_table()
    lab, _ = water.labels()
    d = add_baselines(d, lab)
    sp, provisional = choose_split(d)
    train, val, test = (take(d, *sp[k]) for k in ("train", "val", "test"))
    print(f"split={'PROVISIONAL ' if provisional else ''}{sp}\nrows train={len(train)} val={len(val)} test={len(test)}")
    m = lgb.train(PARAMS, lgb.Dataset(train[water.FEATURES], train.exceed.astype(int)), 3000,
                  valid_sets=[lgb.Dataset(val[water.FEATURES], val.exceed.astype(int))],
                  callbacks=[lgb.early_stopping(150, verbose=False)])
    iso = IsotonicRegression(out_of_bounds="clip").fit(m.predict(val[water.FEATURES]), val.exceed.astype(int))
    t = test.copy()
    t["prob"] = iso.predict(m.predict(t[water.FEATURES]))
    t["week"] = t.date.dt.to_period("W").astype(str)

    period = {k: [str(a or d.date.min().date()), str(b or d.date.max().date())] for k, (a, b) in sp.items()}
    metrics = {"provisional_split": provisional, "period": period,
               "inputs": "Scored with actual (ERA5) rain, an upper bound on live accuracy"}
    for region, g in [("all", t), ("south_bay", t[t.south_bay]), ("rest", t[~t.south_bay])]:
        metrics[region] = {c: scores(g, c) for c in ["prob", "last_ratio", "rain_rule"]}
    auc = lambda c: (lambda g: roc_auc_score(g.exceed.astype(int), g[c].fillna(0)) if g.exceed.nunique() > 1 else np.nan)
    metrics["auc_ci"] = {c: block_bootstrap(t, "week", auc(c), n=300) for c in ["prob", "last_ratio", "rain_rule"]}
    metrics["by_lead"] = {int(k): scores(g, "prob") for k, g in t.groupby("lead_k")}
    metrics["beats_baseline"] = bool(metrics["all"]["prob"]["auc"] > max(metrics["all"][c].get("auc", 0)
                                                                          for c in ["last_ratio", "rain_rule"]))
    stations = st.reset_index()[["station", "name", "beach", "lat", "lon", "dist_mouth_km", "south_bay", "point_id"]]
    save("water", {"model.txt": m, "feature_list.json": water.FEATURES, "metrics.json": metrics,
                   "thresholds.json": {"levels": LEVELS, "standard": water.THRESHOLD},
                   "calibration.json": {"x": iso.X_thresholds_.tolist(), "y": iso.y_thresholds_.tolist()},
                   "stations.json": stations.to_dict("records"),
                   "station_categories.json": [str(c) for c in train.station.cat.categories]})
    for region in ["all", "south_bay", "rest"]:
        print(region, {c: {k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()}
                       for c, s in metrics[region].items()})
    print("AUC CI:", {c: (round(v["value"], 3), [round(x, 3) for x in v["ci95"]]) for c, v in metrics["auc_ci"].items()})
    print("by lead:", {k: round(v.get("auc", np.nan), 3) for k, v in metrics["by_lead"].items()})
    print("beats baseline:", metrics["beats_baseline"])


if __name__ == "__main__":
    main()
