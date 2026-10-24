"""AQI conversion matches EPA breakpoint tables (values from EPA's Technical Assistance Document, 2024)."""
import pandas as pd

from pipeline.features.air import O3_8H_BP, PM25_BP, aqi, daily_aqi_from_hourly


def test_pm25_breakpoints():
    assert aqi(9.0, PM25_BP, 1) == 50
    assert aqi(9.1, PM25_BP, 1) == 51
    assert aqi(35.4, PM25_BP, 1) == 100
    assert aqi(35.49, PM25_BP, 1) == 100  # truncated to one decimal before lookup
    assert aqi(55.5, PM25_BP, 1) == 151


def test_ozone_breakpoints():
    assert aqi(0.054, O3_8H_BP, 3) == 50
    assert aqi(0.070, O3_8H_BP, 3) == 100
    assert aqi(0.071, O3_8H_BP, 3) == 101
    assert aqi(0.0859, O3_8H_BP, 3) == 150


def test_daily_from_hourly():
    t = pd.date_range("2026-07-01 07:00", periods=24, freq="h", tz="UTC")  # 00:00–23:00 PDT on Jul 1
    pm = pd.DataFrame({"site": "060730001", "parameter": "pm25", "ts_utc": t, "conc": 12.0})
    o3 = pd.DataFrame({"site": "060730001", "parameter": "ozone", "ts_utc": t, "conc": [40.0] * 12 + [72.0] * 12})
    d = daily_aqi_from_hourly(pd.concat([pm, o3])).set_index("parameter")
    assert d.loc["pm25", "aqi"] == aqi(12.0, PM25_BP, 1)
    assert d.loc["ozone", "aqi"] == aqi(0.072, O3_8H_BP, 3) == 105  # 104.5 rounds up
