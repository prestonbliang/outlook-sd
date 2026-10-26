"""Freshness budgets for the source data actually used by each forecast."""
# Hourly feeds get 6 h, matching the app's forecast window: GitHub's scheduler often runs the "hourly" job
# every 2-4 hours, and a forecast built from 4-hour-old inputs is still valid.
SOURCE_STALE_HOURS = {"ibwc": 6, "noaa_tides": 6, "airnow": 6, "cdip": 6, "calheatscore": 26,
                      "beachwatch": 240, "sd_fire_ems": 87 * 24, "firms": 24, "openmeteo": 6,
                      "nws": 6, "calfire": 24, "calfire_year": 26, "apcd": 240, "cool_zones": 8 * 24}
# EMS call-level features lag 90 days; reserve three days for future target dates.
