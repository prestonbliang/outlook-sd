# Models and limitations

Outlook SD publishes estimates for San Diego neighborhoods. Official warnings and posted closures take precedence. Availability varies with source freshness and coverage; the Data page shows current timestamps.

## Forecast targets

| Hazard | Target | Main coverage limit |
| --- | --- | --- |
| Beach water | Probability of a bacteria exceedance at the nearest monitored beach | Appearance and community observations cannot establish bacteria levels; water evaluation is provisional. |
| Air | PM2.5 and ozone AQI at monitoring sites | Nearby monitors are an approximation for neighborhood conditions. |
| Heat | Estimated heat-associated excess emergency calls per ZIP | City of San Diego Fire-Rescue coverage; other ZIPs use state CalHeatScore where available. Per-resident levels require population data. |
| Coastal flooding | Water levels at upcoming high tides | One San Diego Bay gauge; the map is not a street-level inundation model. |
| Wildfire | Relative risk of a new fire growing beyond 10 acres | Map levels are ranks, not calibrated neighborhood probabilities. |

Forecast generation and the map cover today and the next three Pacific dates when inputs are available. The homepage planning brief shows three days. Some hazards or places have shorter or unavailable coverage.

## Held-out evaluation

The committed evaluations compare models with simple baselines on held-out dates. Most results use observed weather (ERA5), making them optimistic relative to live forecasts. Flood also includes a separate archived-weather forecast evaluation, identified below. The live Track record scores forecasts when their outcomes become available; it is separate from these retrospective results.

**Flood.** Test period Jan 2025 → Oct 14, 2026. With the weather forecasts that were actually available at the time (Open-Meteo archived runs), the error is 0.112 ft and 69 of 81 minor-flood days were caught with 13 false alarms (persistence: 69 caught, 16 false alarms). The table below uses actual weather.

| | Outlook SD | Persistence (yesterday's offset) | Tide only |
|---|---|---|---|
| Residual RMSE, ft (95% CI) | **0.108** (0.100–0.117) | 0.145 (0.138–0.153) | 0.453 |
| Minor-flood days caught | **70 of 81** (12 false alarms) | 69 of 81 (16 false alarms) | 0 of 81 |

Tropical Storm Rachel replay (forecast issued Oct 9, 5 am PT): forecast peaks of 11.54, 11.79 and 11.84 ft STND against observed peaks of 11.49, 11.71 and 11.64 ft. That is minor flooding correctly called on all three days. The tide alone predicted no flooding.

**Heat.** Test period Jan 2025 → Aug 31, 2026, the last EMS date included in this evaluation.

| | Outlook SD | Normal-weather model | Same day last week |
|---|---|---|---|
| Calls per ZIP per day, MAE | **3.19** | 3.22 | 4.38 |
| Citywide calls per day, MAE | **28.5** | 31.7 | 35.6 |
| Hot-day excess error (14 days) | 37.6 | — | **32.7** |

The model underpredicts heat-wave excess calls: the hot test days averaged 26 predicted excess calls against 56 observed. The "same day last week" baseline performs better on the hot-day excess-error measure.

**Air.** PM2.5 test period: January 2025–April 29, 2026; ozone test period: calendar year 2025. AQI error (MAE): PM2.5 8.6 (95% CI 7.8–9.3) vs 12.4 for yesterday's AQI; ozone 5.0 (4.5–5.6) vs 7.2. The median forecasts detected none of the actual "Unhealthy for sensitive groups" monitor-days; the ozone median also produced two false alarms. By comparison, the high-end forecast caught 57 of 80 such ozone monitor-days (181 false alarms) vs 10 for yesterday's AQI.

**Fire.** Test period Jan 2025 → Oct 17, 2026: 46 new fires reached 10 acres in 1.9 million area-days. 30 of 46 started in an area rated High or Very high that day. Flagging the same 2.4% of area-days as Red Flag Warnings, the model caught 10 fires and the Red Flag rule caught 3. Ranking skill: AUC-PR 2.7× the fire rate (month only 2.0×, Red Flag days 1.1×), AUC-ROC 0.77 (month only 0.71). The Brier score is no better than the month-only average, so the levels are best read as ranks.

Henderson Fire replay (Oct 15, 2026): county-wide risk jumped to 0.13–0.15 expected large fires per day (normal 0.08), and 43–65% of areas were rated High. But the coastal Camp Pendleton area where it started was rated only Moderate.

**Water.** Provisional split: test Jan → May 2021. Border-flow history for 2021-06 onward is pending.

| AUC | Outlook SD | Last test result | Rain rule (0.1 in) |
|---|---|---|---|
| All beaches (95% CI) | **0.854** (0.817–0.890) | 0.822 | 0.536 |
| South Bay | **0.809** | 0.786 | 0.526 |
| Rest of county | **0.870** | 0.813 | 0.517 |

Brier score 0.071; recall at 80% precision 0.28, vs 0.22 for the last test result.

Source metrics: [Water](../models/artifacts/water/metrics.json), [Heat](../models/artifacts/heat/metrics.json), [Flood](../models/artifacts/flood/metrics.json), [Air](../models/artifacts/air/metrics.json), [Fire](../models/artifacts/fire/metrics.json). No models were retrained for the v1.0 release.

## Interpretation limits

- Water laboratory results and emergency-call outcomes can arrive well after a forecast. Scoring waits for available outcomes; an unscored forecast is not a success.
- Heat-wave excess calls are underpredicted in the held-out evaluation. Fire ranking skill does not establish calibrated fire probabilities. Air high-end forecasts can raise many false alarms.
- CalHeatScore has no public historical archive in this project and is compared only on logged live days.
- Fire labels after 2020 use CAL FIRE incident/perimeter locations, which can approximate ignition points. The hazard-zone layer covers State Responsibility Areas.
- AirNow API observations can fall back to keyless public hourly files. FIRMS refreshes need a separate NASA key. Failed providers can leave older stored inputs; the app shows freshness and unavailable states.
- The South Bay odor display is a complaint record, not a smell forecast. The committed odor experiment found no improvement from weather over recent complaints (Brier gain −0.003; 95% CI −0.017 to +0.012).
- The river-flow scenario is a learned association, not a causal estimate. The sea-level scenario shifts historical gauge readings and excludes waves and local subsidence.
- Community observations are unverified and never change forecast probabilities. Browser counts do not establish unique people or trustworthy witnesses. See [Community safeguards](COMMUNITY_SAFEGUARDS.md).
