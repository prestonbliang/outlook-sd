"""Probe: FPA FOD (reads the downloaded GDB zip)"""
from pipeline.sources import fpa_fod as s
from pipeline.sources._common import probe_report

probe_report("fpa_fod_sd", s.fetch_history().drop(columns="geometry"), "DISCOVERY_DATE")
