"""'What if' scenarios for the policy page, plus the Water reliability table for the Track record.

Border flow: rerun the trained Water model on 2017–2021 South Bay samples (the years with flow data) with the
river's flow features capped at each level. This is the model's estimate, not a measured effect.
Sea level: add a fixed rise to every observed hourly water level at the bay gauge (2014–2025) and count the days
per year that reach NOAA's minor-flood level. No model involved.
"""
import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from models.common import ART, save
from pipeline.features import flood, water

M3S_PER_MGD = 0.0438126
FLOW = ["q_24h", "q_72h", "q_7d", "q_max_7d"]
CAPS_MGD = list(range(0, 105, 5))
RISES_FT = [r / 4 for r in range(0, 13)]


def water_model():
    art = ART / "water"
    m = lgb.Booster(model_file=str(art / "model.txt"))
    cal = json.loads((art / "calibration.json").read_text())
    cats = json.loads((art / "station_categories.json").read_text())
    return lambda x: np.interp(m.predict(x[water.FEATURES]), cal["x"], cal["y"]), cats


def flow_scenario(d, prob):
    sb = d[d.south_bay & (d.lead_k == 0) & (d.date >= "2017-01-01")]
    rows = []
    for cap in CAPS_MGD:
        x = sb.copy()
        x[FLOW] = x[FLOW].clip(upper=cap * M3S_PER_MGD)
        rows.append({"cap_mgd": cap, "unsafe_share": round(float((prob(x) >= 0.5).mean()), 4)})
    p = prob(sb)
    return {"period": f"{sb.date.min().date()} → {sb.date.max().date()}", "samples": int(len(sb)),
            "observed_unsafe_share": round(float(sb.exceed.mean()), 4),
            "no_cap_unsafe_share": round(float((p >= 0.5).mean()), 4), "caps": rows}


def sea_level_scenario():
    thr = json.loads((ART / "flood" / "thresholds.json").read_text())["minor"]
    t = flood.load_tides().observed_ft.dropna()
    t = t[(t.index >= "2014-01-01") & (t.index < "2026-01-01")]
    daily = t.groupby(t.index.tz_convert("America/Los_Angeles").date).max()
    years = len(daily) / 365.25
    return {"period": "2014–2025", "minor_flood_ft_mllw": round(thr - 3.79, 2),
            "rises": [{"rise_ft": r, "days_per_year": round(float((daily + r >= thr).sum() / years), 1)} for r in RISES_FT]}


def reliability(d, prob):
    """Predicted chance vs how often the beach actually failed, on the held-out test samples."""
    from models.train_water import choose_split, take
    sp, _ = choose_split(d)
    t = take(d, *sp["test"])
    t = t.assign(p=prob(t), bin=pd.cut(prob(t), np.linspace(0, 1, 6), include_lowest=True))
    g = t.groupby("bin", observed=True).agg(predicted=("p", "mean"), observed=("exceed", "mean"), n=("p", "size"))
    return [{"predicted": round(float(r.predicted), 3), "observed": round(float(r.observed), 3), "n": int(r.n)}
            for r in g.itertuples() if r.n >= 20]


def main():
    prob, cats = water_model()
    d, _ = water.training_table()
    d["station"] = pd.Categorical(d.station.astype(str), categories=cats)
    out = {"flow": flow_scenario(d, prob), "sea_level": sea_level_scenario()}
    save("scenarios", {"scenarios.json": out})
    save("water", {"reliability.json": reliability(d, prob)})
    print(json.dumps(out)[:600])
    print(json.loads((ART / "water" / "reliability.json").read_text()))


if __name__ == "__main__":
    main()
