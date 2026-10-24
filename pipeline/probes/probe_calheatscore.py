"""Probe: CalHeatScore live (3 ZIPs)"""
from pipeline.sources import calheatscore as s
from pipeline.sources._common import probe_report

probe_report("calheatscore", s.fetch_live(["92154", "92173", "91932"]), "target_date")
