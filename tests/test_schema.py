"""Schema tests for processed tables: required columns, types, and no observed timestamps in the future."""
import pandas as pd
import pytest

from pipeline.sources._common import PROCESSED

NOW = pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=1)
TABLES = {
    "ibwc_flow": (["ts_utc", "stage_m", "discharge_m3s", "source", "tz_source"], "ts_utc"),
    "tides_9410170": (["ts_utc", "observed_ft", "predicted_ft", "residual_ft", "tz_source"], None),
    "cdip_191": (["ts_utc", "hs_m", "tp_s", "dp_deg", "sst_c", "tz_source"], "ts_utc"),
    "beach_results": (["date", "Result", "Unit", "Station_id", "tz_source"], "date"),
    "ems_daily_zip": (["date", "zip", "calls", "calls_medical", "tz_source"], "date"),
    "airdata_daily": (["date", "site_id", "parameter", "aqi", "value", "tz_source"], "date"),
    "calheatscore_log": (["zip", "issued", "lead_days", "chs", "target_date"], "issued"),
}


@pytest.mark.parametrize("name", TABLES)
def test_columns_and_no_future(name):
    path = PROCESSED / f"{name}.parquet"
    if not path.exists():
        pytest.skip(f"{name} not built (run make history)")
    df = pd.read_parquet(path)
    cols, tcol = TABLES[name]
    assert set(cols) <= set(df.columns), set(cols) - set(df.columns)
    assert len(df) > 0
    if tcol:
        t = pd.to_datetime(df[tcol])
        t = t.dt.tz_localize("UTC") if t.dt.tz is None else t
        assert t.max() <= NOW, f"{name} has future timestamps: {t.max()}"


def test_tides_observed_not_in_future():
    if not (PROCESSED / "tides_9410170.parquet").exists():
        pytest.skip("tides not built (run make history SOURCES=tides)")
    df = pd.read_parquet(PROCESSED / "tides_9410170.parquet")
    assert df.loc[df.observed_ft.notna(), "ts_utc"].max() <= NOW  # predictions may extend into the future


def test_ems_counts_are_nonnegative_integers():
    if not (PROCESSED / "ems_daily_zip.parquet").exists():
        pytest.skip("EMS history not built (run make history SOURCES=ems)")
    df = pd.read_parquet(PROCESSED / "ems_daily_zip.parquet")
    assert (df.calls >= 0).all() and (df.calls_medical <= df.calls).all()
    assert df.zip.str.fullmatch(r"\d{5}").all()
