# Run and validate Outlook SD

The repository contains trained models and a San Diego basemap. The historical source tables, live forecast database, generated API files, service keys, and deployment credentials are not committed. A fresh checkout starts without live forecasts.

## Local setup

Use Python 3.12+ with uv and Node 22. From the repository root:

```bash
uv sync --frozen
cd web
npm ci
cd ..
cp .env.example .env
uv run python scripts/check_setup.py
```

Both Python and Next read the root `.env`. Set AirNow and FIRMS keys for those sources. For community reporting, configure the Supabase URL and **anon public key**, never a service-role key. Rebuild the web app after changing public environment variables.

To inspect the app before downloading source data:

```bash
make init
make web
```

`make init` exports all API contracts with explicit missing-data states. It does not create fake forecasts or sample user observations. The basemap, neighborhood picker, and map controls can be explored; live layers need source data.

## Restore existing forecast state

If the GitHub repository already has a release tagged `state`, authenticate the GitHub CLI and run from the repository root:

```bash
gh release download state -p state.tar.gz
scripts/state.sh unpack
make refresh
```

Do not run `make history` or retrain the committed models just to restore an existing deployment. `make refresh` fetches sources, makes forecasts, logs and scores them, and exports the static API. Individual source failures appear as stale/unavailable inputs.

## Bootstrap source data when no state is available

```bash
make probe
make history
make refresh
```

History downloads can be large and may be limited by source quotas. To retry a particular step, use `make history SOURCES="geo acs"` or another name from `pipeline/history.py`. Geography must come before ACS. The included model artifacts can be used once their required input tables are present; `make train` is for a deliberate model rebuild and will replace model artifacts.

Important remaining data dependencies:

- Heat population levels need `data/processed/acs_zcta.parquet`: `make history SOURCES=acs`. Missing population means no per-capita heat level, not Low risk.
- Recent border-flow history is a manual IBWC AQUARIUS export. Put the CSV at `data/raw/ibwc/portal_export.csv` and run `make history SOURCES=ibwc`. The parser expects a `Timestamp (UTC-08:00),Value (...)` header. Until the missing history has been obtained and a new evaluation run, keep the water split described as provisional.
- Air forecasts require AirNow observations and their API key. NOAA, Open-Meteo, CDIP, and the other public sources must also be reachable.
- ZIP/coastal polygon layers need the geography history step. Fire polygons need the cached fire grid and inference. Date-specific fire cells are written by each live run.

After changing geography, run `python scripts/sync_report_places.py` and reapply the Supabase schema so the reporting whitelist matches the app.

## Connect community observations

1. Create/open your Supabase project.
2. Run the entire `supabase/schema.sql` in its SQL Editor, including when upgrading the older reporting implementation. It is repeatable and preserves existing reports. It installs the neighborhood whitelist, insert policy, repeat limits, daily counts, and recent-coverage RPC.
3. Set `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` in `.env`, Vercel's Production/Preview environment variables and GitHub Actions secrets. Copy them from the project's Connect dialog / Settings → API Keys. Legacy `NEXT_PUBLIC_SUPABASE_ANON_KEY` also works; the publishable key takes precedence when both are set. Use only browser-safe keys.
4. Rebuild the web app. Visit a coastal neighborhood, submit an observation, and confirm that its count and freshness update on the hazard page and map.
5. Optionally run `supabase/tests.sql` in the SQL Editor. All its test data is rolled back. Run it during development, since the tests temporarily insert reports inside a transaction.

Reporting requires browser storage and a secure context (HTTPS or localhost). Raw rows and browser codes are never exposed to public readers. Anonymous browser codes discourage repeat submissions; clearing storage or using another device can bypass that identity, so report counts must never be presented as verified people or model confidence.

Coverage is calculated separately for each neighborhood and hazard over the past 24 hours or 7 days. Fewer than three reporting browsers is a participation gap, not a hazard assessment. If reporting is disconnected or fails to load, coverage is unknown. Map observations remain historical observations when a future forecast day is selected.

## Build and test

```bash
uv run pytest -q tests
cd web
npm run test:unit
cd ..
make build
cd web
npm run typecheck
npx playwright install --with-deps chromium firefox webkit
npm run test:e2e
```

Core API and leakage tests use isolated fixtures and require no source downloads. Processed-data schema tests run when their datasets exist and otherwise skip with an explanation. Build before running type checks so Next generates its route declarations. Browser tests need a completed static build. Community browser tests need a build with reporting enabled and `E2E_REPORTS_ENABLED=1` when running Playwright; CI uses a dummy public endpoint intercepted by Playwright, with no actual submissions.

The complete fixture-build commands are in [RELEASE.md](RELEASE.md). The browser suite runs in Chromium, Firefox and WebKit and includes automated WCAG A/AA checks. Linux browser dependencies must match a supported Playwright host (CI uses Ubuntu). `npm run assets` copies self-hosted fonts and the MapLibre module worker; both `dev` and `build` run it automatically.

To serve the built app: `cd web && npx http-server out`. `make web` starts Next development mode using the exported JSON. `make api` separately exposes the FastAPI endpoints for inspection; the frontend reads exported JSON from `web/public/api` in both modes.

## Hosted hourly operation

See [VERCEL.md](VERCEL.md) for project linking, Actions secrets, first launch, and the prebuilt deployment/check workflow.

The hourly workflow requires the `state` release asset. For first-time setup, build the source tables and perform a live run locally, then:

```bash
scripts/state.sh pack
gh release create state --title "Outlook SD pipeline state" --notes "Processed source data and the forecast log."
gh release upload state state.tar.gz --clobber
```

Configure `AIRNOW_API_KEY`, `FIRMS_MAP_KEY`, the two Supabase public settings, and `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` in GitHub Actions secrets. Set `NWS_USER_AGENT` as a repository variable with a project contact. The hourly workflow restores and saves state, refreshes forecasts, exports the API, builds, validates the live snapshot, packages Vercel's prebuilt output, deploys, and checks the site. Do not publish the fixture build produced by the separate checks workflow.
