"""Leakage tests: changing any observation AFTER the issue time must not change a forecast-time feature."""
import numpy as np
import pandas as pd

from pipeline.features import flood, heat, water


def test_flood_state_uses_only_past_observations():
    tides, waves = flood.load_tides(), flood.load_waves()
    for issue in pd.DatetimeIndex(["2025-03-01 12:00", "2025-08-15 00:00"], tz="UTC"):
        before = flood.state_at(tides, waves, pd.DatetimeIndex([issue]))
        t2, w2 = tides.copy(), waves.copy()
        t2.loc[t2.index > issue, "residual_ft"] = 99.0
        w2.loc[w2.index > issue, ["hs_m", "tp_s", "sst_anom"]] = 99.0
        pd.testing.assert_frame_equal(before, flood.state_at(t2, w2, pd.DatetimeIndex([issue])))


def test_water_flow_features_use_days_before_issue():
    fd = water.flow_daily()
    issue = pd.Timestamp("2019-02-10")
    before = water.flow_features(fd).loc[issue]
    fd2 = fd.copy()
    fd2.loc[fd2.index >= issue, ["mean", "max"]] = 999.0
    after = water.flow_features(fd2).loc[issue]
    pd.testing.assert_series_equal(before, after)


def test_heat_call_level_lags_at_least_90_days():
    ems = pd.read_parquet(heat.PROCESSED / "ems_daily_zip.parquet").assign(date=lambda x: pd.to_datetime(x.date))
    target = pd.Timestamp("2025-07-01")
    lvl = heat.call_level(ems).set_index(["date", "zip"]).level_365d
    ems2 = ems.copy()
    ems2.loc[ems2.date > target - pd.Timedelta(days=90), "calls"] = 10_000
    lvl2 = heat.call_level(ems2).set_index(["date", "zip"]).level_365d
    a, b = lvl.xs(target, level="date"), lvl2.xs(target, level="date")
    assert np.allclose(a.sort_index(), b.sort_index())


def test_flood_rows_never_use_observed_target_as_feature():
    d = flood.training_table().head(5000)
    assert "residual" not in flood.FEATURES and "observed" not in flood.FEATURES
    assert (d.target > d.issue).all()
