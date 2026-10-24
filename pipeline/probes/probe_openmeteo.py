"""Probe: Open-Meteo archive, forecast, previous runs"""
from pipeline.sources import openmeteo as s
from pipeline.sources._common import probe_report

p = s.grid_points().iloc[10]
probe_report("openmeteo_archive", s.archive(p.point_id, p.lat, p.lon, "2024-07-01", "2024-07-02"), "ts_utc")
probe_report("openmeteo_forecast", s.forecast(s.grid_points().iloc[:3]), "ts_utc")
probe_report("openmeteo_previous", s.previous_runs(p.point_id, p.lat, p.lon, "2026-10-01", "2026-10-02"), "ts_utc")
