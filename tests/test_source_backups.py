"""Backups for flaky feeds: the wave buoy from NOAA's copy, AirNow readings from the public hourly files."""
import pandas as pd

from pipeline.sources import airnow, cdip

NDBC = """#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE
#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   hPa  degC  degC  degC  nmi  hPa    ft
2026 10 25 01 56  MM   MM   MM   1.3    14   7.4 198     MM    MM  24.6    MM   MM   MM    MM
2026 10 25 01 26  MM   MM   MM    MM    MM    MM  MM     MM    MM    MM    MM   MM   MM    MM
"""


def test_ndbc_copy_maps_to_cdip_columns_and_drops_empty_rows():
    d = cdip.parse_ndbc(NDBC)
    assert len(d) == 1
    r = d.iloc[0]
    assert (r.ts_utc, r.hs_m, r.tp_s, r.dp_deg, r.sst_c) == (pd.Timestamp("2026-10-25 01:56", tz="UTC"), 1.3, 14, 198, 24.6)


def test_cdip_outage_fills_only_hours_after_the_last_erddap_reading(tmp_path, monkeypatch):
    monkeypatch.setattr(cdip, "PROCESSED", tmp_path)
    monkeypatch.setattr("pipeline.sources._common.PROCESSED", tmp_path)
    pd.DataFrame({"ts_utc": [pd.Timestamp("2026-10-25 01:30", tz="UTC")], "station": "191", "hs_m": 1.0, "tp_s": 12.0,
                  "dp_deg": 200.0, "sst_c": 24.0, "tz_source": "UTC"}).to_parquet(tmp_path / "cdip_191.parquet")

    def fake_get(source, url, *a, **k):
        if "erddap" in url:
            raise RuntimeError("cdip_191: HTTP 500")
        return type("R", (), {"text": NDBC.replace("01 26  MM   MM   MM    MM    MM    MM  MM",
                                                   "01 26  MM   MM   MM   1.2    15   7.2 198")})
    monkeypatch.setattr(cdip, "get", fake_get)
    out = cdip.fetch_live()
    assert list(out.ts_utc.dt.strftime("%H:%M")) == ["01:30", "01:56"]  # the 01:26 copy row is already covered


def test_airnow_files_backup_keeps_san_diego_pm25_and_ozone(monkeypatch):
    text = ("10/25/26|00:00|060730001|Chula Vista|-8|OZONE|PPB|54|San Diego APCD\n"
            "10/25/26|00:00|060730001|Chula Vista|-8|PM2.5|UG/M3|-999|San Diego APCD\n"
            "10/25/26|00:00|060731006|Alpine|-8|NO2|PPB|4|San Diego APCD\n"
            "10/25/26|00:00|060371103|Los Angeles|-8|OZONE|PPB|40|South Coast AQMD\n")
    monkeypatch.setattr(airnow, "get", lambda *a, **k: type("R", (), {"text": text}))
    d = airnow.observations_from_files(hours=1)
    assert list(d.parameter) == ["ozone", "pm25"]
    assert d.conc.iloc[0] == 54 and pd.isna(d.conc.iloc[1])  # negative sentinel is missing, not zero
    assert str(d.ts_utc.iloc[0]) == "2026-10-25 00:00:00+00:00"


def test_airnow_api_failure_falls_back_without_the_official_forecast(tmp_path, monkeypatch):
    monkeypatch.setattr(airnow, "PROCESSED", tmp_path)
    monkeypatch.setattr("pipeline.sources._common.PROCESSED", tmp_path)
    monkeypatch.delenv("AIRNOW_API_KEY", raising=False)
    monkeypatch.setattr(airnow, "observations_from_files", lambda hours: pd.DataFrame(
        {"ts_utc": [pd.Timestamp("2026-10-25", tz="UTC")], "site": ["060730001"], "parameter": ["ozone"], "conc": [54.0]}))
    obs, fc = airnow.fetch_live()
    assert len(obs) == 1 and fc.empty and (tmp_path / "airnow_obs.parquet").exists()
