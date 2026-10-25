"""Leakage tests: changing any observation AFTER the issue time must not change a forecast-time feature."""
import numpy as np
import pandas as pd

from pipeline.features import air, flood, heat, water


def test_flood_state_uses_only_past_observations():
    times = pd.date_range("2025-01-01", "2025-09-01", freq="h", tz="UTC")
    tides = pd.DataFrame({"residual_ft": np.sin(np.arange(len(times)))}, index=times)
    waves = pd.DataFrame({"hs_m": 1., "tp_s": 10., "sst_anom": .5}, index=times)
    for issue in pd.DatetimeIndex(["2025-03-01 12:00", "2025-08-15 00:00"], tz="UTC"):
        before = flood.state_at(tides, waves, pd.DatetimeIndex([issue]))
        t2, w2 = tides.copy(), waves.copy()
        t2.loc[t2.index > issue, "residual_ft"] = 99.0
        w2.loc[w2.index > issue, ["hs_m", "tp_s", "sst_anom"]] = 99.0
        pd.testing.assert_frame_equal(before, flood.state_at(t2, w2, pd.DatetimeIndex([issue])))


def test_water_flow_features_use_days_before_issue():
    times = pd.date_range("2019-01-01", "2019-03-01")
    fd = pd.DataFrame({"mean": 1., "max": 2., "n": 24}, index=times)
    issue = pd.Timestamp("2019-02-10")
    before = water.flow_features(fd).loc[issue]
    fd2 = fd.copy()
    fd2.loc[fd2.index >= issue, ["mean", "max"]] = 999.0
    after = water.flow_features(fd2).loc[issue]
    pd.testing.assert_series_equal(before, after)


def test_heat_call_level_lags_at_least_90_days():
    dates = pd.date_range("2023-01-01", "2025-12-31")
    ems = pd.DataFrame([(d, z, 10 + d.day % 5) for d in dates for z in ["92101", "92109"]],
                       columns=["date", "zip", "calls"])
    target = pd.Timestamp("2025-07-01")
    lvl = heat.call_level(ems).set_index(["date", "zip"]).level_365d
    ems2 = ems.copy()
    ems2.loc[ems2.date > target - pd.Timedelta(days=90), "calls"] = 10_000
    lvl2 = heat.call_level(ems2).set_index(["date", "zip"]).level_365d
    a, b = lvl.xs(target, level="date"), lvl2.xs(target, level="date")
    assert np.allclose(a.sort_index(), b.sort_index())


def test_flood_rows_never_use_observed_target_as_feature():
    times = pd.date_range("2025-01-01", periods=240, freq="h", tz="UTC")
    tides = pd.DataFrame({"predicted_ft": 5., "residual_ft": .2, "observed_ft": 5.2}, index=times)
    waves = pd.DataFrame({"hs_m": 1., "tp_s": 10., "sst_anom": .5}, index=times)
    weather = pd.DataFrame({c: 1. for c in flood.WX}, index=times)
    issue = pd.DatetimeIndex([times[168]])
    d = flood.build(issue, tides, weather, waves)
    changed = tides.copy()
    changed.loc[changed.index > issue[0], ["residual_ft", "observed_ft"]] = 999.
    after = flood.build(issue, changed, weather, waves)
    assert "residual" not in flood.FEATURES and "observed" not in flood.FEATURES
    assert (d.target > d.issue).all()
    pd.testing.assert_frame_equal(d[flood.FEATURES], after[flood.FEATURES])


def test_live_air_can_use_yesterday_when_today_has_no_complete_aqi_yet():
    issue = pd.Timestamp("2026-10-25")
    history = pd.DataFrame({"site": "test", "date": pd.date_range("2026-10-18", "2026-10-24"), "aqi": range(1, 8)})
    sites = pd.DataFrame({"point_id": ["p"]}, index=pd.Index(["test"], name="site"))
    weather = {"p": pd.DataFrame({c: [1.] for c in ["tmax", "tmin", "rh_mean", "sw_sum", "wind_mean", "wind_max", "blh_max", "precip", "offshore_hours"]}, index=[issue])}
    lab = pd.DataFrame({"site": ["test"], "date": [issue]})
    before = air.build(lab, sites, history, weather)
    row = before[before.lead_k == 0].iloc[0]
    assert row.aqi_prev == 7 and row.aqi_prev_mean7 == 4
    # Today's partial reading and any future outcomes must not enter today's issued features.
    future = pd.concat([history, pd.DataFrame({"site": "test", "date": [issue, issue + pd.Timedelta(days=1)], "aqi": 9999})])
    after = air.build(lab, sites, future, weather)
    pd.testing.assert_frame_equal(before[air.FEATURES], after[air.FEATURES])
    missing_yesterday = air.build(lab, sites, history[history.date < "2026-10-24"], weather)
    assert pd.isna(missing_yesterday[missing_yesterday.lead_k == 0].iloc[0].aqi_prev)
