"""Fire: LightGBM classifier P(new fire ≥10 acres starts in a 2 km cell on a day), with isotonic calibration.

Train 2014–2023 on all fire cell-days plus a weighted 1% sample of quiet cell-days; early-stop and calibrate on
2024; test on every cell-day in 2025–26. Baselines: NWS Red Flag days (county-wide) and month-only climatology.
"""
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from models.common import save
from pipeline.features import fire
from pipeline.sources._common import PROCESSED

TZ = "America/Los_Angeles"
PARAMS = dict(objective="binary", learning_rate=0.03, num_leaves=15, min_data_in_leaf=50, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=5.0, verbose=-1)


def full_grid(g, wx, start, end):
    """Every cell × every day in [start, end] with features (for unbiased evaluation and level cut-offs)."""
    days = pd.date_range(start, end)
    rows = pd.DataFrame({"cell": np.repeat(g.cell.to_numpy(), len(days)), "date": np.tile(days, len(g))})
    rows = rows.merge(g[["cell", "point_id", *fire.STATIC]], on="cell").merge(wx, on=["point_id", "date"], how="inner")
    rows["month"] = rows.date.dt.month
    return rows


def red_flag_days():
    w = pd.read_parquet(PROCESSED / "nws_warnings.parquet")
    w = w[(w.phenomena == "FW") & (w.significance == "W")]
    days = set()
    for a, b in zip(w.utc_issue.dt.tz_convert(TZ), w.utc_expire.dt.tz_convert(TZ)):
        days.update(pd.date_range(a.normalize().tz_localize(None), b.normalize().tz_localize(None)))
    return days


def main():
    rows, g, lab, wx = fire.training_table()
    train, val = rows[rows.date <= "2023-12-31"], rows[(rows.date >= "2024-01-01") & (rows.date <= "2024-12-31")]
    print(f"train rows={len(train)} (fires {train.y.sum()}), val rows={len(val)} (fires {val.y.sum()})")
    m = lgb.train(PARAMS, lgb.Dataset(train[fire.FEATURES], train.y, weight=train.w), 3000,
                  valid_sets=[lgb.Dataset(val[fire.FEATURES], val.y, weight=val.w)],
                  callbacks=[lgb.early_stopping(150, verbose=False)])
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0).fit(m.predict(val[fire.FEATURES]), val.y, sample_weight=val.w)

    # level cut-offs: 75th / 90th / 98th percentiles of calibrated probability over every 2023 cell-day
    ref = full_grid(g, wx, "2023-01-01", "2023-12-31")
    ref_p = iso.predict(m.predict(ref[fire.FEATURES]))
    cuts = dict(zip(["moderate", "high", "very_high"], np.quantile(ref_p, [0.75, 0.90, 0.98]).tolist()))

    test = full_grid(g, wx, "2025-01-01", wx.date.max())
    test["p"] = iso.predict(m.predict(test[fire.FEATURES]))
    pos = lab[lab.date >= "2025-01-01"][["cell", "date"]].drop_duplicates().assign(y=1)
    test = test.merge(pos, on=["cell", "date"], how="left").fillna({"y": 0})
    month_rate = train.groupby("month").apply(lambda x: np.average(x.y, weights=x.w), include_groups=False)
    test["clim"] = test.month.map(month_rate)
    rf = red_flag_days()
    test["red_flag"] = test.date.isin(rf).astype(float)
    y = test.y.astype(int)
    lvl = np.select([test.p >= cuts["very_high"], test.p >= cuts["high"], test.p >= cuts["moderate"]],
                    ["very_high", "high", "moderate"], "low")
    fires = test[y == 1].assign(level=lvl[y.to_numpy() == 1])
    alarm = test.red_flag.mean()  # share of cell-days a Red Flag rule flags
    top = test.p >= np.quantile(test.p, 1 - alarm) if alarm > 0 else pd.Series(False, index=test.index)
    metrics = {
        "period": {"train": "2014 → 2023", "val": "2024", "test": f"2025-01 → {test.date.max():%Y-%m-%d}"},
        "inputs": "Scored with actual (ERA5) weather, an upper bound on live accuracy",
        "test_cell_days": int(len(test)), "test_fires": int(y.sum()), "base_rate": float(y.mean()),
        "auc_pr": {"model": float(average_precision_score(y, test.p)), "climatology": float(average_precision_score(y, test.clim)),
                   "red_flag": float(average_precision_score(y, test.red_flag))},
        "auc_roc": {"model": float(roc_auc_score(y, test.p)), "climatology": float(roc_auc_score(y, test.clim))},
        "brier": {"model": float(brier_score_loss(y, test.p)), "climatology": float(brier_score_loss(y, test.clim))},
        "fires_by_level": fires.level.value_counts().reindex(["low", "moderate", "high", "very_high"], fill_value=0).to_dict(),
        "fires_high_or_above": int(fires.level.isin(["high", "very_high"]).sum()),
        "same_alarm_rate": {"share_flagged": float(alarm), "red_flag_caught": int(test.red_flag[y == 1].sum()),
                            "model_caught": int(top[y == 1].sum())},
        "levels": cuts,
    }
    metrics["beats_baseline"] = bool(metrics["auc_pr"]["model"] > max(metrics["auc_pr"]["climatology"], metrics["auc_pr"]["red_flag"]))

    # replays: county-wide expected large fires per day, and the fire's own cell
    def replay(name, start, end, cell_dates):
        win = full_grid(g, wx, start, end)
        win["p"] = iso.predict(m.predict(win[fire.FEATURES]))
        daily = win.groupby("date").p.sum()
        out = {"name": name, "days": [{"date": f"{d:%Y-%m-%d}", "expected_fires": round(float(v), 3),
                                       "share_cells_high": round(float((win[win.date == d].p >= cuts["high"]).mean()), 3)}
                                      for d, v in daily.items()],
               "normal_expected_fires": round(float(ref_p.sum() / 365), 3), "fires": []}
        for cell, date, fname in cell_dates:
            day = win[win.date == date]
            r = day[day.cell == cell]
            if len(r):
                pc = float(r.p.iloc[0])
                out["fires"].append({"name": fname, "date": f"{date:%Y-%m-%d}", "cell": cell, "probability": pc,
                                     "level": next((k for k in ["very_high", "high", "moderate"] if pc >= cuts[k]), "low"),
                                     "percentile_that_day": round(float((day.p < pc).mean() * 100), 1)})
        return out

    hend = lab[lab.name.fillna("").str.contains("Henderson") & (lab.date >= "2026-01-01")]
    jan25 = lab[(lab.date >= "2025-01-06") & (lab.date <= "2025-01-12")]
    metrics["replays"] = [
        replay("Henderson Fire week (Oct 13–19, 2026)", "2026-10-13", min(pd.Timestamp("2026-10-19"), wx.date.max()),
               [(r.cell, r.date, r.name) for r in hend.itertuples()]),
        replay("January 2025 Santa Ana winds (Jan 6–12, 2025)", "2025-01-06", "2025-01-12",
               [(r.cell, r.date, r.name) for r in jan25.itertuples()]),
    ]
    save("fire", {"model.txt": m, "feature_list.json": fire.FEATURES, "metrics.json": metrics,
                  "thresholds.json": {"levels": cuts, "min_acres": fire.MIN_ACRES},
                  "calibration.json": {"x": iso.X_thresholds_.tolist(), "y": iso.y_thresholds_.tolist()}})
    print({k: v for k, v in metrics.items() if k not in ("replays", "levels")})
    for rp in metrics["replays"]:
        print(rp["name"], "normal/day:", rp["normal_expected_fires"])
        print(pd.DataFrame(rp["days"]).to_string(index=False)); print(rp["fires"])
    print("beats baseline:", metrics["beats_baseline"])


if __name__ == "__main__":
    main()
