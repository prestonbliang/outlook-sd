# Credits

Outlook SD is built from public data and open-source software. This file records data and software attribution, development tools, and the student contributions documented during development.

## Datasets

| Dataset | Publisher | License | Used for |
|---|---|---|---|
| Gauge 11-0133.00, Tijuana River at International Boundary (live telemetry) | U.S. Section, International Boundary and Water Commission | U.S. government work (public domain) | Water: border flow |
| Tijuana River Discharge and Suspended Sediment Concentration (HydroShare d2f31999…) | HydroShare; IBWC gage data | CC BY 4.0 | Water: border-flow history 2000–2021 |
| Beach Water Quality Monitoring: results, stations, advisories (Beach Watch) | California State Water Resources Control Board, via data.ca.gov | Open Data Commons Attribution (ODC-BY) | Water: outcome labels |
| CDIP buoys 191 (Point Loma South) and 155 (Imperial Beach), via CeNCOOS ERDDAP | Coastal Data Information Program, Scripps Institution of Oceanography | Freely available; acknowledgement requested | Water, Flood: waves, ocean temperature |
| CO-OPS stations 9410170 (San Diego) and 9410230 (La Jolla): water levels, predictions, datums, flood levels | NOAA | U.S. government work (public domain) | Flood: labels, tide predictions, thresholds |
| ERA5 reanalysis, forecasts and archived forecasts (Open-Meteo APIs) | Open-Meteo (ECMWF ERA5 and national weather models) | CC BY 4.0 — "Weather data by Open-Meteo.com" | All tiles: weather |
| Active alerts (api.weather.gov) | National Weather Service | U.S. government work (public domain) | Flood, Fire: official warnings |
| NWS warning archive (VTEC) | Iowa Environmental Mesonet, Iowa State University | Freely available | Baselines |
| Fire-Rescue calls for service 2016–2026 | City of San Diego (data.sandiego.gov) | Open Data Commons PDDL | Heat: labels |
| CalHeatScore (live API) | CalEPA / OEHHA | State of California open data (no license listed) | Heat: comparison and fallback rating |
| EPA AirData daily PM2.5 (88101) and ozone (44201) | U.S. EPA | U.S. government work (public domain) | Air: training labels |
| AirNow API | U.S. EPA | U.S. government work (public domain) | Air: live hourly observations (daily AQI computed with EPA breakpoints) |
| AirNow public hourly data files (files.airnowtech.org) | U.S. EPA | U.S. government work (public domain) | Air: backup for hourly observations when the API is down or no key is set |
| NDBC station 46232 realtime data (same buoy as CDIP 191) | NOAA National Data Buoy Center | U.S. government work (public domain) | Water, Flood: backup wave readings when CDIP's ERDDAP is down |
| California Historic Fire Perimeters; CAL FIRE incident API | CAL FIRE | State of California public information | Fire |
| Spatial wildfire occurrence data 1992–2020, 6th ed. (FPA FOD, RDS-2013-0009.6) | USDA Forest Service | U.S. government work (public domain) | Fire: labels 2014–2020 |
| Fire Hazard Severity Zones in State Responsibility Areas (FHSZ in SRA) | CAL FIRE | State of California public information | Fire: hazard share per 2 km cell |
| FIRMS VIIRS active-fire detections | NASA | Freely available; acknowledgement requested | Fire: satellite detections |
| Cartographic boundaries (county, ZCTA, places), TIGER roads and area water, Gazetteer | U.S. Census Bureau | U.S. government work (public domain) | Neighborhoods, ZIPs, shoreline, roads |
| ACS 2019–2023 5-year summary files (tables B01003, B01001, B19013, B25035) | U.S. Census Bureau | U.S. government work (public domain) | Heat: population for per-resident levels; context |
| Community reports (one-tap, structured) | Outlook SD users, stored in Supabase | Collected by this app; public aggregate summaries | Shown next to forecasts; compared with forecasts; never used for training |
| Community planning areas | City of San Diego | Open Data Commons PDDL | Named neighborhoods |
| Air-quality complaint log, 2018 → present (Complaint-Report.xlsx) | San Diego County Air Pollution Control District | Public records dataset (no license listed) | South Bay sewage-smell record; odor-forecast test (not shipped) |
| Cool Zones (hosted feature layer) | County of San Diego HHSA, via SANDAG GIS | Public GIS layer (no license listed) | Nearest air-conditioned public places on Heat and Air |
| State of California Sea Level Rise Guidance, 2024 update | California Ocean Protection Council | State of California public information | "What if" page: context sentence only |
| Protomaps daily basemap build (OpenStreetMap data) | Protomaps; OpenStreetMap contributors | ODbL (© OpenStreetMap contributors) | Map background |

Water exceedance standards: 104 MPN or CFU per 100 mL for culture methods (California 17 CCR §7958); 1,413 DNA copies per 100 mL for ddPCR (Crain et al., 2021; EPA Region 9 approval for San Diego County, May 2022).

## Libraries

Python: pandas 3.1 (BSD-3), NumPy 2.5 (BSD-3), PyArrow 26 (Apache-2.0), requests 2.34 (Apache-2.0), LightGBM 4.7 (MIT), scikit-learn 1.9 (BSD-3), GeoPandas 1.2 (BSD-3), Shapely 2.2 (BSD-3), pyogrio 0.13 (MIT), pyproj 3.8 (MIT), FastAPI 0.162 (MIT), Uvicorn 0.54 (BSD-3), HTTPX 0.28 (BSD-3), python-dotenv 1.2 (BSD-3), pytest 9.1 (MIT).

Web: Next.js 16.4 (MIT), React 19.3 (MIT), U.S. Web Design System 3.14 (CC0 / Apache-2.0; Public Sans font under SIL OFL 1.1), MapLibre GL JS 6.4.1 (BSD-3), react-map-gl 8.1 (MIT), PMTiles 4.5 (BSD-3), Protomaps basemaps 5.7 (BSD-3), Observable Plot 0.6 (ISC), TypeScript 5.9 (Apache-2.0), Playwright 1.64 (Apache-2.0), axe-core/Playwright 4.14 (MPL-2.0, development tests only).

Self-hosted map glyphs and sprites come from [Protomaps basemaps-assets](https://github.com/protomaps/basemaps-assets/tree/028c18f713baecad011301ff7a69acc39bcc2ae7). Noto Sans glyphs use the SIL Open Font License; sprites derive from MIT-licensed Tangram icons. Source provenance and licenses are included in `web/public/map-assets/`. The MapLibre worker and shared module are copied from the installed package at build time with its BSD license.

Tools: go-pmtiles 1.31 (BSD-3) to cut the San Diego basemap; uv (Astral) for Python environments; GitHub Actions; Vercel; Supabase (Postgres + PostgREST) for community reports; PostgreSQL 17 container for isolated database tests. Earlier local tests also used postgres:16 and postgrest/postgrest v12.2.3.

## AI tools

**Claude Code (Anthropic; model Claude Opus 5.5)** was used in this project to:

- turn the project brief into a build plan;
- probe every data source and write the ingestion code (`pipeline/sources/`);
- write the feature builders, training scripts and evaluation (`pipeline/features/`, `models/`);
- write the hourly pipeline, the API, the static export and the GitHub Actions workflow;
- write the Next.js front end, the tests, and the first drafts of README.md and this file;
- design and test the community-report database schema (`supabase/schema.sql`) and report features, after a teammate proposed crowdsourcing.

**Codex (OpenAI)** was used for repository audits and code changes across the frontend, source handling, static export and deployment tooling. This included the visual redesign, planning and saved-place comparisons, map fixes, community summaries and token-protected withdrawal, reporting migrations, deployment fixes, documentation and release preparation. It also wrote and ran regression, browser, accessibility and database checks. Validation evidence is recorded in [STATUS.md](docs/STATUS.md).

The running app does not call a generative-AI or language-model service. Forecasts use trained LightGBM machine-learning models. Verdicts and advice use the fixed tables in `api/verdicts.json` and `api/actions.json`; community summaries use deterministic text derived from selected observations. AI development assistance is described above, separately from runtime behavior.

### Student contributions

The student proposed crowdsourced condition reports and an interactive San Diego map, defined reporting blind spots as part of crowdsourcing, selected Vercel for deployment, and directed iterative development and quality assurance. The implementation assistance is described above.
