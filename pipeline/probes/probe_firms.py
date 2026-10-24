"""Probe: FIRMS VIIRS NRT, last 3 days (needs key)"""
from pipeline.sources import firms as s
from pipeline.sources._common import probe_report

probe_report("firms", s._fetch("VIIRS_SNPP_NRT", 3))
