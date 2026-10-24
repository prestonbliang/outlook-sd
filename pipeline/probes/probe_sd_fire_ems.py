"""Probe: Fire-EMS current-year file"""
from pipeline.sources import sd_fire_ems as s
from pipeline.sources._common import probe_report

probe_report("sd_fire_ems", s.year_file(2026, refresh=True), "date_response")
