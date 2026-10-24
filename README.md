# Outlook SD

A 3-day, neighborhood-level forecast for five hazards in San Diego County: beach water quality, air quality, heat, coastal flooding and wildfire. Each forecast comes from a model trained on real local outcomes. The app logs every forecast it makes and scores it once the real outcome arrives.

Outlook SD is a forecast, not an official advisory. Every tile links to the official source.

## Map and community observations

The Map page lets users switch hazards and forecast days, inspect stations and shaded areas, search neighborhoods or ZIPs, and submit observations for a selected neighborhood. A neighborhood list provides the same selection controls without requiring WebGL. On small screens the controls and map stack vertically.

Community observations include counts, time since the latest report, and coverage over the past 24 hours or 7 days. Reporting blind spots are places with fewer than three reporting browsers for the selected hazard and time window. They ask for more observations; they are not risk ratings or confidence scores. Browser codes are not verified people. The app stores no precise user coordinates, names, emails, or free text. Reports never modify the forecast.

Community reporting requires Supabase configuration and the current `supabase/schema.sql`, including its `report_summary` function. Disconnected or failed requests show coverage as unavailable. Reports remain observations about recent conditions when a future forecast day is selected.

## What each tile forecasts

| Tile | Question | Unit | Status |
|---|---|---|---|
| Water | Will bacteria exceed the state standard at the nearest monitored beach? | Beach Watch station-day | Model live (provisional split, see below) |
| Heat | How many extra emergency calls will heat cause in my ZIP? | ZIP-day, City of San Diego Fire-Rescue area | Model live; levels need ACS population |
| Flood | How high will the bay and coast get at the next high tides? | Hourly water level, NOAA 9410170 | Model live |
| Air | AQI for PM2.5 and ozone | Monitor-day | Model trained (beats persistence); live forecasts start once the AirNow key is set |
| Fire | Chance a new fire starts and grows past 10 acres | 2 km cell-day | Model live; levels are ranks (riskiest 25 / 10 / 2% of days) |

## Results on held-out data

Each model was trained on earlier years and scored on years it never saw, against a simple baseline. These scores use the weather that actually happened (ERA5), so they are an upper bound on live accuracy. The live log on the Track record page measures real forecast skill.

**Flood.** Test period Jan 2025 → Oct 14, 2026. With the weather forecasts that were actually available at the time (Open-Meteo archived runs), the error is 0.112 ft and 69 of 81 minor-flood days were caught with 13 false alarms (persistence: 69 caught, 16 false alarms). The table below uses actual weather.

| | Outlook SD | Persistence (yesterday's offset) | Tide only |
|---|---|---|---|
| Residual RMSE, ft (95% CI) | **0.108** (0.100–0.117) | 0.145 (0.138–0.153) | 0.453 |
| Minor-flood days caught | **70 of 81** (12 false alarms) | 69 of 81 (16 false alarms) | 0 of 81 |

Tropical Storm Rachel replay (forecast issued Oct 9, 5 am PT): forecast peaks of 11.54, 11.79 and 11.84 ft STND against observed peaks of 11.49, 11.71 and 11.64 ft. That is minor flooding correctly called on all three days. The tide alone predicted no flooding.

**Heat.** Test period Jan 2025 → Aug 31, 2026, the last published EMS date.

| | Outlook SD | Normal-weather model | Same day last week |
|---|---|---|---|
| Calls per ZIP per day, MAE | **3.19** | 3.22 | 4.38 |
| Citywide calls per day, MAE | **28.5** | 31.7 | 35.6 |
| Hot-day excess error (14 days) | 37.6 | — | **32.7** |

The model under-calls heat waves: on hot test days it expected 26 extra calls and 56 arrived. On that hot-day measure it loses to the "same day last week" baseline. We report this rather than hide it.

**Air.** Test year 2025. AQI error (MAE): PM2.5 8.6 (95% CI 7.8–9.3) vs 12.4 for yesterday's AQI; ozone 5.0 (4.5–5.6) vs 7.2. The median forecast never reaches "Unhealthy for sensitive groups"; the high-end forecast caught 57 of 80 such ozone monitor-days (181 false alarms) vs 10 for yesterday's AQI.

**Fire.** Test period Jan 2025 → Oct 17, 2026: 46 new fires reached 10 acres in 1.9 million area-days. 30 of 46 started in an area rated High or Very high that day. Flagging the same 2.4% of area-days as Red Flag Warnings, the model caught 10 fires and the Red Flag rule caught 3. Ranking skill: AUC-PR 2.7× the fire rate (month only 2.0×, Red Flag days 1.1×), AUC-ROC 0.77 (month only 0.71). The Brier score is no better than the month-only average, so the levels are best read as ranks.

Henderson Fire replay (Oct 15, 2026): county-wide risk jumped to 0.13–0.15 expected large fires per day (normal 0.08), and 43–65% of areas were rated High. But the coastal Camp Pendleton area where it started was rated only Moderate.

**Water.** Provisional split: test Jan → May 2021. Border-flow history for 2021-06 onward is pending.

| AUC | Outlook SD | Last test result | Rain rule (0.1 in) |
|---|---|---|---|
| All beaches (95% CI) | **0.854** (0.817–0.890) | 0.822 | 0.536 |
| South Bay | **0.809** | 0.786 | 0.526 |
| Rest of county | **0.870** | 0.813 | 0.517 |

Brier score 0.071; recall at 80% precision 0.28, vs 0.22 for the last test result.

Full metrics: `models/artifacts/<tile>/metrics.json`.

## Known limits

- **Beach Watch** San Diego results end Mar 4, 2026. Water forecasts are scored live only when new samples are published.
- **City Fire-Rescue calls** are published about two months late (data runs through Aug 31, 2026). Heat forecasts can't be scored for recent weeks.
- **CalHeatScore** has no public history, so it is compared on live days only. Logging started Oct 23, 2026.
- **Heat model coverage:** City of San Diego Fire-Rescue ZIPs only. Other ZIPs show the state CalHeatScore.
- **Flood** uses one gauge, San Diego Bay. The map marks shoreline places, not individual streets.
- **Fire** labels after 2020 come from CAL FIRE incidents and perimeter centroids, so some ignition points are approximate. The hazard-zone layer covers State Responsibility Areas only.
- **Air** live forecasts need the AirNow key. AirNow's own forecast becomes the comparison baseline from the day the key is added.
- **Community reports** are unverified, rate-limited and published only as counts. They never change a forecast.

## How it works

```
GitHub Actions (hourly)
  restore state (GitHub release asset "state")
  pipeline/run_all.py   fetch live sources → predict days 0–3 → log to data/outlook.db → score matured forecasts
  api/export.py         render every FastAPI response to web/public/api/*.json
  next build            static site (web/out)
  vercel deploy         publish
  save state
```

- `pipeline/sources/`: one module per data source (`fetch_live`, `fetch_history`). `pipeline/probes/`: one probe script per source.
- `pipeline/features/`: feature builders per tile, with plain-language labels for the "why" lines.
- `models/train_<tile>.py`: training and evaluation. Artifacts go to `models/artifacts/<tile>/`.
- `api/main.py`: the FastAPI app (`/places`, `/outlook`, `/hazard/{tile}`, `/map/{tile}`, `/track-record`, `/health`).
- `web/`: Next.js app (Today, Detail, Map, Track record, Data).

## Run it

Needs Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 22.

For a fresh clone, use the complete [setup and deployment guide](docs/SETUP.md). Run `make doctor` to see which dependencies, source tables, and service settings are missing. Run `make init` after dependency installation to explore the app with explicit missing-data states before restoring source data. Existing deployments should restore the `state` release rather than download and retrain everything.

For Vercel, follow the [Vercel launch guide](docs/VERCEL.md). The manual `deploy-vercel` workflow supports an explicit first launch before forecast state exists. Both deployment workflows validate and package `.vercel/output` for `vercel deploy --prebuilt`, then check the hosted pages, API, and map byte-range support.

```bash
cp .env.example .env          # add AIRNOW_API_KEY, FIRMS_MAP_KEY (free) and the Supabase URL + anon key
uv sync
make probe                    # check every data source
make history                  # download and process history (≈1 GB peak, mostly temporary)
make train                    # deliberately rebuild all five models (overwrites artifacts)
uv run python -m pipeline.run_all   # one live run: forecasts into data/outlook.db
uv run python -m api.export   # static API for the web app
cd web && npm ci && npm run build && npx http-server out   # or: make api / make web for development
make test                     # pytest (schema, leakage, API contract) + Playwright smoke test
```

`make refresh` combines the live pipeline and API export. `make build` exports the API and builds the site. Core API and leakage tests run on fixtures without the historical archive; processed-data schema tests require their source tables. Browser tests require a completed static build. See the setup guide for type checks, browser installation, Supabase database tests, and the first state-release upload.

### Community reports (Supabase)

1. Create a free project at supabase.com.
2. Open **SQL Editor**, paste [`supabase/schema.sql`](supabase/schema.sql) and run it. It creates an insert-only `reports` table with row-level security, a neighborhood whitelist, per-browser repeat limits, daily counts, and a recent-coverage summary. Reapply the full schema when upgrading from the older reporting implementation; existing reports are preserved.
3. From **Project Settings → API**, copy the project URL and the `anon` public key into `.env` as `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and add both as GitHub Actions secrets.

The anon key is meant to be public: with the schema's policies it can only add reports and read counts. Raw rows and device IDs are never readable.

Dataset licenses, libraries and AI-tool use are listed in [CREDITS.md](CREDITS.md).
