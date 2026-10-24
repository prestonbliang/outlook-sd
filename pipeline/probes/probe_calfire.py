"""Probe: CAL FIRE perimeters + incidents"""
from pipeline.sources import calfire as s
from pipeline.sources._common import probe_report

probe_report("calfire_incidents", s.incidents([2026]), "StartedDateOnly")
probe_report("calfire_perimeters", s.perimeters(2024).drop(columns="geometry"), "date")
