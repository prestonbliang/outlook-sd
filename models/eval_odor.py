"""Sewage odor in South Bay: can weather forecast it beyond what recent complaints already say?

Label: a day with ≥3 APCD odor complaints from South Bay ZIPs. The complaint log runs ~3 days behind, so the
"recent reports" baseline uses the 7 days ending 7 days before the target. Train 2024-01 → 2025-03, test 2025-07 →.
Result decides what the app shows: a forecast only if weather adds skill with a 95% CI above zero, otherwise the
recent complaint record itself.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

from models.common import block_bootstrap, save
from pipeline.sources._common import PROCESSED
from pipeline.sources.apcd import SOUTH_BAY

TZ = "America/Los_Angeles"
POINT = "g32.50_-117.00"  # ERA5 cell over the Tijuana River valley
WEATHER = ["night_calm", "night_wind", "night_blh", "night_rh", "rain_14d"]


def daily_counts():
    c = pd.read_parquet(PROCESSED / "odor_complaints.parquet")
    c = c[c.zip.isin(SOUTH_BAY)]
    days = pd.date_range("2018-01-01", c.date.max())
    return c.groupby(pd.to_datetime(c.date)).size().reindex(days, fill_value=0)


def night_weather():
    """Night of date D = 18:00 D-1 → 09:00 D local, when complaints about trapped odor peak."""
    w = pd.read_parquet(PROCESSED / f"weather_{POINT}.parquet").set_index("ts_utc").sort_index()
    w.index = w.index.tz_convert(TZ).tz_localize(None) + pd.Timedelta(hours=6)
    w["calm"] = (w.wind_speed_10m < 1.5).astype(float)
    n = w[w.index.hour < 15].groupby(w[w.index.hour < 15].index.normalize())
    x = pd.DataFrame({"night_calm": n.calm.mean(), "night_wind": n.wind_speed_10m.mean(),
                      "night_blh": n.boundary_layer_height.mean(), "night_rh": n.relative_humidity_2m.mean()})
    x["rain_14d"] = w.precipitation.groupby(w.index.normalize()).sum().rolling(14).sum()
    return x


def main():
    c = daily_counts()
    d = night_weather().reindex(c.index).assign(n=c, y=(c >= 3).astype(int))
    d["recent"] = np.log1p(c.shift(7).rolling(7).mean())
    d = d.dropna()
    train, test = d["2024-01-01":"2025-03-31"], d["2025-07-01":]

    def fit(cols):
        mu, sd = train[cols].mean(), train[cols].std()
        lr = LogisticRegression(max_iter=2000).fit((train[cols] - mu) / sd, train.y)
        return lr.predict_proba((test[cols] - mu) / sd)[:, 1]

    t = test.assign(base=fit(["recent"]), model=fit(["recent", *WEATHER]), week=test.index.to_period("W").astype(str))
    gain = block_bootstrap(t, "week", lambda g: brier_score_loss(g.y, g.base) - brier_score_loss(g.y, g.model))
    hi = t[t.n.shift(7).rolling(7).mean().reindex(t.index).fillna(0) >= 1]
    metrics = {
        "period": {"train": "2024-01-01 → 2025-03-31", "test": f"2025-07-01 → {t.index.max().date()}"},
        "label": "Day with 3 or more South Bay odor complaints to APCD",
        "test_days": int(len(t)), "event_days": int(t.y.sum()),
        "brier": {"recent_reports": brier_score_loss(t.y, t.base), "recent_plus_weather": brier_score_loss(t.y, t.model)},
        "auc": {"recent_reports": roc_auc_score(t.y, t.base), "recent_plus_weather": roc_auc_score(t.y, t.model)},
        "weather_brier_gain": gain,
        "calm_night_correlation": float(np.corrcoef(hi.night_calm, hi.n)[0, 1]),
        "weather_adds_skill": bool(gain["ci95"][0] > 0),
    }
    save("odor", {"metrics.json": metrics})
    print(metrics)


if __name__ == "__main__":
    main()
