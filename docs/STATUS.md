# Final implementation and QA status

Updated October 24, 2026. Outlook SD is a locally tested release candidate. It is not deployed, and its live source archive and reporting service are not configured in this checkout. See [RELEASE.md](RELEASE.md) for reproducible QA, launch requirements and a competition demonstration.

Vercel GitHub integration is now configured explicitly in the root `vercel.json`. A local Vercel CLI production build successfully emitted one static web service, all 690 API JSON files, and no serverless functions. The Git build supports safe optional runtime-state restoration; the prebuilt hourly path uses the same service layout. See [VERCEL.md](VERCEL.md) for the required project settings and environment-variable locations. The counts below describe the prior finalization pass; deployment-specific regressions are covered additionally in `tests/test_vercel_git.py` and the web packaging unit tests.

Deployment follow-up verification: **65 Python tests passed, 9 existing source-data tests skipped; 27 frontend unit tests and 15 browser smoke/journey executions passed.** Strict TypeScript, Ruff, shell syntax, the Git build with uv bootstrap, and prebuilt service packaging passed. Enabling the live-forecast requirement correctly rejected the state-free build. The local Vercel CLI used temporary fixture project settings and did not contact or change a hosted project.

## Real-data verification (Oct 24, 2026, maintainer checkout with restored state)

Run against the actual processed source tables, forecast log and all 32 weather archives (not fixtures):

- Python suite: **75 passed, 0 skipped**. The 9 source-data tests skipped in the clean checkout pass with the real files.
- Live `pipeline.run_all`: Flood, Water, Heat and Fire forecasts produced. The first live scores were logged: Flood 2 of 2 matched; Fire scored county-wide.
- Web: 27 unit tests and **84 of 84** Playwright executions passed (Chromium, Firefox, WebKit). Supabase schema applied twice and `supabase/tests.sql` passed on PostgreSQL 17.
- **Fixed:**
  - the static export crashed once a Fire score existed (Fire has no yes/no hit, so `SUM(hit)` is NULL); a regression test was added;
  - `.eyebrow` labels were rendered in ALL CAPS at 12 px, against the brief's sentence-case rule and type scale; they are now sentence case at 14 px;
  - the Codex disclosure was moved from "Student contributions" to "AI tools" in CREDITS;
  - the macOS-WebKit skip-link test now uses Option+Tab (Safari's default Tab behavior skips links).

## Completed

- Cohesive navigation, responsive hazard cards, saved neighborhoods, shareable map views, browser history restoration, loading/error recovery and keyboard controls.
- Pacific-date forecast freshness, explicit unavailable states, honest observation timestamps, independently displayed official warnings, and stale incident handling. Required stale inputs do not establish deployment readiness.
- Shared reporting reads, aggregate validation, preserved duplicate rejection, no automatic submission retries, and private-key rejection before browser builds.
- Atomic runtime source/map writes, database indexes and cleanup, content-based model versions, credential redaction, and failing probe exit codes.
- Fixed a production map-worker URL defect that left the canvas blank. Worker modules, fonts and sprites are now served locally. Map readiness is covered by browser tests.
- Fixed accessibility defects found by axe: visible/accessibility name mismatch, missing search-result references, and invalid generated chart ARIA. Exact chart values remain available in accessible tables.
- Patched MapLibre to 6.4.1, added strict unused-code checking, and blocked test reporting builds from deployment.

## Executed verification

- Full Python suite with the locked dependencies: **59 passed, 9 skipped**. The nine existing processed-source tests skip because the required historical files are absent; no new tests were disabled.
- **26 frontend unit tests passed.**
- **84 Playwright executions passed:** 28 scenarios in Chromium, Firefox and WebKit, including 15 automated WCAG A/AA page checks, four viewport widths (320, 390, 768, 1440), actual map rendering/fallback, navigation/history, sharing, saved places, charts, denied location/storage, errors/retries, and reporting success/outage/duplicate rejection. No browser tests skipped.
- Production Next.js static build and complete strict TypeScript checks passed.
- PostgreSQL 17: schema applied/reapplied successfully; SQL tests passed for permissions/RLS, hazard/place validation, hourly limits, repeat rejection and summaries. A two-session concurrent duplicate test stored one report and rejected the other. The database was isolated and temporary.
- Six live provider smoke checks parsed responses successfully: NWS, CAL FIRE, CalHeatScore, IBWC telemetry, NOAA gauge and Open-Meteo. Temporary files were removed; no runtime source archive was fabricated.
- npm audit and pip-audit reported **zero known vulnerabilities** for the installed dependencies.
- Vercel Build Output packaging passed with explicit QA flags. Packaging rejected the test reporting build without its QA override. The deployment script has no test-build override.
- The read-only deployment checker passed against the locally served static export, including 110 neighborhoods and PMTiles HTTP range support. This was not a hosted Vercel check.
- Ruff 0.17.2 correctness/unused-import checks, Python/JavaScript syntax, workflow YAML parsing, and Git whitespace checks passed. Three unused Python imports were removed. Desktop/mobile screenshots were inspected.

Nonblocking test-tool warnings remain from Starlette's legacy HTTPX adapter and the development static server. They did not fail the checks; no production application warning was suppressed.

## Required before public launch

1. Restore/bootstrap actual source tables and the forecast database; configure AirNow/FIRMS/contact settings; run the pipeline and verify genuinely current forecasts and scoring. The repository's `state` release returned 404 when checked. Existing model weights/evaluations were preserved.
2. Configure the real Supabase project, apply/verify its schema/RLS, set both public build values, and verify a real report updates coverage. Local PostgreSQL tests do not prove the hosted service is configured.
3. Configure the existing Vercel project credentials, rebuild with real settings, deploy a preview, and run the hosted checks. The QA fixture build cannot be deployed through the deployment script. No public deployment, remote database mutation, or GitHub push occurred.
4. Inspect the real-data preview on intended devices and assistive technologies, and complete a truthful competition recording. Water evaluation remains provisional; the documented model limits still apply.

The app covers water, air, heat, coastal flooding, fire, maps and community observations. Energy/outage/GridLab features are not present and are not claimed.
