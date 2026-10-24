"""Probe: EPA AirData daily PM2.5 current year (SD)"""
from pipeline.sources import airdata as s
from pipeline.sources._common import probe_report

probe_report("airdata_pm25", s.year("88101", 2026), "Date Local")
