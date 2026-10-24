"""Probe: IBWC live telemetry file"""
from pipeline.sources import ibwc as s
from pipeline.sources._common import probe_report

probe_report("ibwc_live", s.parse_live(s.get("ibwc", s.LIVE_URL).text), "ts_utc")
