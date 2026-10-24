# Outlook SD engineering and product audit

October 24, 2026. Improvements are in the existing codebase. This describes implementation and local verification, not a verified production deployment.

## Architecture and priorities

The app has substantial existing foundations: five trained hazard models, source-specific ingestion/features, a SQLite forecast/score log, FastAPI-to-static-JSON export, a Next.js static site, a MapLibre/PMTiles map, aggregate Supabase reporting, and GitHub Actions/Vercel publishing.

The audit covered frontend routes/components/hooks, API/export contracts, pipeline orchestration/source utilities/features, training/evaluation code and committed artifacts, Supabase schema/tests, packaging/deployment scripts, workflows, and setup documentation. Existing scientific assumptions and the deployment architecture were preserved.

The largest product risks were misleading freshness, disconnected navigation/reporting workflows, unreliable empty/error states, interpretation of anonymous reports, and operational failure recovery. Personalization and sharing improve real neighborhood workflows without collecting exact coordinates or inventing observations. Reporting blind spots remain part of crowdsourcing.

## Implemented changes

| Area | Improvement |
| --- | --- |
| Forecast trust | Pacific-date selection, explicit current/stale/unavailable states, date-bearing timestamps, last-observed air labels, and API quality metadata. Tomorrow never becomes today's verdict. |
| Official warnings | NWS warnings independent of model availability, unknown status for stale feeds, and links to NWS. |
| Navigation | Shared header, active navigation, validated/remembered place selection, page titles, and integrated detail/map/report links. |
| Personalization | Up to eight saved neighborhoods on this device, quick switching, corrupt-storage handling, and a session fallback when storage is blocked. |
| Map workflows | Share links preserve neighborhood/hazard/day/reporting window; browser history restores controls; clipboard fallback exposes a selectable URL. |
| Production map rendering | Explicit self-hosted module worker fixes bundler rewriting to an HTML page; local glyphs/sprites remove third-party asset dependencies. Actual map readiness is tested across browsers. |
| Design | Coastal visual system, cohesive cards/header/panels, clearer action hierarchy, responsive layouts, visible focus and larger controls. |
| Accessibility | Skip link, unique picker IDs, result announcements, labelled tables, textual risk/freshness states, reduced-motion/contrast support, and focus return after place selection. |
| Charts | Resize-aware drawing with cleanup, error fallback, UTC time labels, and expandable exact-values tables. |
| Reporting | Shared coverage reads, visible-page refresh, refresh after save, validated counts/kinds/timestamps, and honest uncertain-submission feedback. |
| Reporting integrity | Existing duplicate rejection and scoped-alert regression preserved. Failed reads do not become zero-report claims. Writes are never retried automatically. |
| Requests | Timeouts, navigation cancellation, one retry for temporary GET server errors, clear errors and explicit retries. |
| Performance | Shared catalogue/cache, coverage subscribers, preindexed map summaries, linear nearest-place scan, deferred mobile homepage map, and lazy chart tables. |
| Source robustness | Invalid AQI/fire numbers and coordinates handled safely; official incident links restricted to the official HTTPS host. |
| Storage | Same-directory temporary writes and atomic replacement protect processed files on interruption; raw filenames include microseconds. |
| Database | Lookup indexes, explicit API connection cleanup, foreign-key enforcement and write busy timeout. |
| Source semantics | Common freshness budgets aligned to required model inputs; EMS allowance matches the 90-day lag and three-day forecast horizon. |
| Reproducibility | Model versions derive from inference-artifact contents rather than checkout timestamps or evaluation-report edits. |
| Pipeline checks | Every source probe attempted; redacted failures produce a nonzero exit code. |
| Security | Encoded credential/query redaction, private Supabase key rejection before bundling, and Vercel framing/object/referrer/permissions headers. |
| Track record | Union of baseline columns prevents missing later comparisons; scrollable labelled tables and retry/loading states. |
| Flood scoring | Date-based exclusion of incomplete current-day observations preserves yesterday's completed peak when today's feed is absent. |

Finalization upgraded MapLibre to its patched 6.4.1 release and added a development-only axe accessibility test dependency. No fabricated forecasts, external database changes, model retraining, or deployments were introduced. Test reporting builds are identified by credential-free metadata and rejected by the deployment script.

## Validation

See [STATUS.md](STATUS.md) for the final executed results. The locked Python suite, frontend unit tests, production build, full TypeScript checks, cross-browser journeys, automated WCAG checks, database validation and dependency audits have now run. Earlier compatibility-runtime/direct-function checks were preliminary evidence and have been superseded by these full checks.

Desktop/mobile screenshots were inspected, and the basemap was verified rendering actual local tiles. Six live source providers returned parseable responses in bounded temporary-file smoke checks. These checks do not replace model inference against restored source archives or a real Supabase/Vercel deployment; neither is configured locally.

The browser suite now contains 28 scenarios, run in Chromium, Firefox and WebKit (84 executions). Reporting scenarios require the test build configuration below; no browser scenarios were skipped in final QA. Discovery targets `*.spec.ts`, preventing Node unit tests from running under Playwright. CI forbids focused tests and retains failure traces/screenshots. The checks workflow also verifies the reporting schema and permissions in PostgreSQL.

## Release verification

Run in a network-enabled checkout with the supported Python/Node versions:

```bash
uv sync --frozen
uv run pytest -q tests
uv run python -m api.export
cd web
npm ci
npm run test:unit
NEXT_PUBLIC_SUPABASE_URL=https://reports.example.invalid NEXT_PUBLIC_SUPABASE_ANON_KEY=test-public-key npm run build
npm run typecheck
npx playwright install --with-deps chromium firefox webkit
E2E_REPORTS_ENABLED=1 npm run test:e2e
cd ..
node scripts/prepare-vercel.mjs --allow-unavailable --allow-test-reporting
```

This creates a fixture reporting build for validation, with genuine unavailable forecast states. Do not publish that fixture build. Build production again with real public reporting configuration and restored/current source data, following [VERCEL.md](VERCEL.md).

Manually verify mobile/wide screens, keyboard focus/history, denied geolocation/storage, failed reads, clipboard fallback, chart/table access, map failure recovery, warning visibility, repeat rejection, and actual report saves refreshing counts. Run `supabase/tests.sql` against an isolated database before verifying production schema/RLS. Confirm PMTiles range support with the existing hosted check.

## Remaining priorities

1. **Verify current live data.** Restore runtime state, set source/reporting/deployment credentials, run probes, and inspect every tile's timestamps/required sources. A static build alone cannot establish live data availability. Inspect hourly runs and hosted snapshot metadata.
2. **Validate reporting and abuse controls.** The schema restricts raw-row reads and limits per-browser repeats, but UUIDs are resettable and do not identify unique people. Measure abuse before choosing server rate limits/challenges. Keep aggregate reports separate from forecast probabilities and define retention/monitoring based on real usage.
3. **Revisit scientific evaluation.** Water evaluation remains provisional pending recent IBWC history. Audit censored laboratory results and the full-record SST climatology for leakage before retraining. Re-evaluate heat-wave underprediction, fire calibration, and air high-end false alarms against documented baselines. Preserve transparent track-record limitations.
4. **Test restored data.** Runtime source tables and forecast state are absent locally. Run schema/leakage/API/browser checks against real state and empty fixtures. Measure chart payloads and map responsiveness before adding workers, virtualization or infrastructure.
5. **Verify the hosted release and intended devices.** Automated accessibility and keyboard checks now pass in three browser engines, and dependency audits reported no known vulnerabilities. Check the configured preview on real devices and with intended assistive technologies before submission; local tests do not establish hosted service configuration.

The next product milestone is a verified live neighborhood workflow: select/save a place, inspect current hazards and official warnings, report an observation, see refreshed coverage, and share the same map view.
