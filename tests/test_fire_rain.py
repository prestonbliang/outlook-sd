"""Live 'days since rain' over a short window must match the full-archive count."""
import numpy as np
import pandas as pd

from pipeline.features import fire


def _hourly(days, wet_days):
    t = pd.date_range("2026-06-01 07:00", periods=24 * days, freq="h", tz="UTC")
    h = pd.DataFrame(index=t, data={"temperature_2m": 25.0, "relative_humidity_2m": 30.0, "wind_speed_10m": 3.0,
                                    "wind_direction_10m": 270.0, "wind_gusts_10m": 6.0, "boundary_layer_height": 800.0,
                                    "shortwave_radiation": 500.0, "precipitation": 0.0})
    for d in wet_days:
        h.loc[t[24 * d], "precipitation"] = 5.0
    return h


def test_short_window_matches_full_archive():
    full = _hourly(60, wet_days=[3, 40])
    archive = fire.fire_weather(full).days_since_rain
    window = full.iloc[24 * 45:]  # last 15 days only, no rain inside
    last = fire.last_rain_before([f"{d:%Y-%m-%d}" for d in archive[archive == 0].index], window.index.min().tz_convert(fire.TZ).normalize().tz_localize(None))
    live = fire.fire_weather(window, last).days_since_rain
    assert np.array_equal(live.to_numpy(), archive.loc[live.index].to_numpy())
