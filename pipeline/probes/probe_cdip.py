"""Probe: CDIP 191 last 3 days"""
from pipeline.sources import cdip as s
from pipeline.sources._common import probe_report

probe_report("cdip_191", s.fetch("191", "2026-10-20"), "ts_utc")
