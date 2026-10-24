"""Freshness budgets for the source data actually used by each forecast."""
SOURCE_STALE_HOURS = {"ibwc": 3, "noaa_tides": 2, "airnow": 3, "cdip": 6, "calheatscore": 26,
                      "beachwatch": 240, "sd_fire_ems": 87 * 24, "firms": 24, "openmeteo": 3,
                      "nws": 3, "calfire": 24}
# EMS call-level features lag 90 days; reserve three days for future target dates.
