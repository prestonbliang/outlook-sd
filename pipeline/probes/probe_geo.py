"""Probe: Census geography: county, ZCTA, places, roads, FHSZ, ACS (needs key)"""
from pipeline.sources import geo as s
from pipeline.sources._common import probe_report

s.fetch_history()
probe_report("zcta_sd", s.zcta().drop(columns="geometry"))
probe_report("places", s.places())
probe_report("acs_zcta", s.acs(s.zcta().zip.tolist()))
