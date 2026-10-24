"""Probe: NOAA tides 9410170 / 9410230, one week"""
from pipeline.sources import noaa_tides as s
from pipeline.sources._common import probe_report

for st in s.STATIONS:
    probe_report(f"noaa_{st}", s.hourly(st, "2026-10-08", "2026-10-14"), "ts_utc")
