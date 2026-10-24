"""Probe: NWS active alerts (SGX)"""
from pipeline.sources import nws as s
from pipeline.sources._common import probe_report

probe_report("nws_alerts", s.fetch_live())
