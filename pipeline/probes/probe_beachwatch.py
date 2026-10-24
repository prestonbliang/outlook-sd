"""Probe: Beach Watch stations (SD)"""
from pipeline.sources import beachwatch as s
from pipeline.sources._common import probe_report

probe_report("beach_stations", s.stations())
