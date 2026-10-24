# Implementation and validation status

This checkout now includes:

- Fresh-clone API exports with missing-data states, explicit unavailable verdicts, expired-forecast filtering, and honest fire-data availability.
- A weather-history bootstrap that creates its previously missing point list, plus Air monitor coverage in live weather requests.
- Isolated pipeline stages for missing optional inputs, date-specific fire polygons, and forecast logging that preserves issued rows and score references on retries.
- An interactive San Diego map with hazard/day controls, inspection popups, neighborhood/ZIP search, county reset, map failure recovery, and a neighborhood list.
- Community observations with freshness, aggregate browser counts, configurable coverage windows, reporting gaps, and submission/error/retry handling.
- A Supabase neighborhood whitelist, concurrent per-browser repeat limits, restricted insert permissions, and a coverage-summary RPC. Apply the full schema to connect these features.
- Fixture-based API, leakage, and browser regression tests, plus a GitHub Actions checks workflow.
- A manual Vercel launch workflow, prebuilt output packaging with freshness checks, public snapshot metadata, and a read-only hosted deployment check including PMTiles byte ranges.

Validated locally:

- SQLite forecast-log, snapshot-readiness, and deployment-check regression tests pass (13).
- Community coverage/vocabulary/freshness and Vercel packaging unit test files pass.
- All Python files compile; TypeScript/TSX files pass syntax transpilation.
- Git whitespace checks pass.

Not yet validated or completed:

- Full Python tests, the Next production build, complete TypeScript checking, browser rendering/tests, and execution of the PostgreSQL schema/tests. Package servers could not be resolved in this environment; required Python and map dependencies are not installed.
- Live source probes and downloads, restoration of historical/forecast state, ACS population download, and the recent IBWC portal export. This checkout has none of those data files.
- Supabase configuration/schema installation, AirNow/FIRMS credentials, deployment credentials, and a hosted deployment. No external database was changed and no site was published.
- New scientific evaluations or model retraining; the committed model artifacts and provisional water evaluation have been preserved.

External checks during the Vercel phase: the GitHub repository was accessible, but its `state` release returned 404. The connected GitHub integration rejected creating a validation tree with HTTP 403 (`Resource not accessible by integration`), so no validation branch was pushed and remote CI has not run. Vercel was discoverable but not connected when checked; no Vercel project settings were inspected or changed.

Use `make doctor` for an up-to-date local diagnosis and `docs/SETUP.md` for the commands to finish validation and service setup. Do not treat the current changes as a verified live deployment.
