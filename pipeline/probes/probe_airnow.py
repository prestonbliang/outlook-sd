"""Probe: AirNow observations + forecast (needs key)"""
from pipeline.sources import airnow as s
from pipeline.sources._common import probe_report

probe_report("airnow_obs", s.observations(6), "ts_utc")
probe_report("airnow_forecast", s.forecast(32.7157, -117.1611))
