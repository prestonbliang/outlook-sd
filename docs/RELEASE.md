# Release candidate and Congressional App Challenge demo

Validated locally on October 24, 2026. The application is not deployed. See [STATUS.md](STATUS.md) for executed checks and remaining operational requirements.

## Product scope

Outlook SD helps San Diego residents understand beach water, air, heat, coastal flooding and fire conditions in the neighborhoods they care about. It combines model forecasts, official warning links, an interactive county map, and structured community observations. Reporting blind spots identify where more observations are needed; they never imply safety. Saved places and shared map views make this a repeatable daily workflow.

Energy dashboards, outage monitoring and GridLab are not implemented features of this repository. They are not part of this release or its claims.

## Reproduce complete QA

Use Python 3.12+, uv, Node 22, and a Playwright-supported host (the CI runner is Ubuntu). From the repository root:

```bash
uv sync --frozen
uvx ruff@0.17.2 check api pipeline models scripts tests --select F,E9
uv run pytest -q tests
uv run python -m api.export
cd web
npm ci
npm run test:unit
NEXT_PUBLIC_SUPABASE_URL=https://reports.example.invalid NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_browser_test_key npm run build
npm run typecheck
npx playwright install --with-deps chromium firefox webkit
E2E_REPORTS_ENABLED=1 npm run test:e2e
cd ..
node scripts/prepare-vercel.mjs --allow-unavailable --allow-test-reporting
```

The public test endpoint is intercepted by Playwright, and synthetic fixtures live only in `web/tests`. The application itself has no fake-live or demo-data mode. The full browser suite exercises Chromium, Firefox and WebKit, automated WCAG A/AA checks, four viewport widths, actual map readiness, sharing/history, saved places, denied permissions/storage, charts, report success/outage/repeat rejection, and error recovery.

The QA package cannot be deployed by `scripts/deploy-vercel.sh`: release metadata marks the test reporting configuration, and the deployment script rejects it. Rebuild with real public settings after QA. `--allow-unavailable` alone never permits test reporting settings.

The `checks` workflow also creates an isolated PostgreSQL service, applies the schema twice, and runs `supabase/tests.sql`, `supabase/observation-options.tests.sql` and `supabase/report-management.tests.sql`. Local database QA covers raw-read denial, restricted timestamps, hazard/type validation, unknown/inland places, hourly limits, duplicate rejection, all observation types, protected owner reads, forged-token rejection, withdrawal retries, rate-limit preservation after withdrawal, deduplicated summaries and moderation. An earlier two-session test verified simultaneous duplicates save exactly one row. Browser QA additionally covers reload recovery, selected-option withdrawal, storage denial, network failures, fallback to older databases and blocked submissions when safeguards cannot be checked.

## Before public release

1. Configure the actual Supabase project and apply/verify `supabase/schema.sql`. Set both public settings in the repository-root `.env` and GitHub Actions secrets. Public builds reject private service-role keys. Verify an actual report saves and updates its count; the local fixtures do not prove the hosted database is configured.
2. Restore or bootstrap the runtime source tables and forecast log using [SETUP.md](SETUP.md). Supply AirNow/FIRMS keys and the project contact for NWS. The `state` release returned 404 when checked; the checkout has no forecast database or source archive. Do not retrain the committed models merely to restore state.
3. Run `make refresh`, inspect source freshness, and confirm real current forecasts. Source-provider availability alone does not prove model inference or scoring against restored state. Packaging rejects a normal live release without current forecast coverage; forecasts whose required inputs are stale do not establish readiness.
4. Set the existing Vercel project IDs/token and follow [VERCEL.md](VERCEL.md). Rebuild with real public settings, package the release, deploy a preview, and run the hosted deployment check. Inspect the preview with real data before publishing production. No Vercel settings, remote database or public site were modified during local QA.

A first launch with explicitly unavailable forecasts remains possible with `--allow-unavailable`, but that is a setup milestone, not a completed live forecast demonstration.

## A focused 60-second demonstration

Use the real configured release; check its timestamps and connectivity before recording.

- **0–15 seconds:** Open Today, select Imperial Beach, and explain the five local hazards. Point to the update time and the difference between a forecast and an official advisory. If a forecast is unavailable, say so.
- **15–30 seconds:** Open Map & reports, select a hazard and forecast day, and inspect an area. Explain that flood coverage is approximate and fire levels are relative ranks. Share the view to preserve the selected place/day/hazard.
- **30–45 seconds:** Show recent community coverage and submit one truthful observation for conditions you are actually observing. Explain that reports never alter forecast probabilities and blind spots describe participation. If reporting is not configured, do not present the submission as working.
- **45–60 seconds:** Show a saved neighborhood and the Track record page. Explain one model result and its limitation, then show the Data page's sources and privacy explanation.

The distinctive value is the combination of transparent local forecasts, an inspectable map, and community coverage without inventing a safety score. Avoid claiming perfect accuracy, verified unique people, street-level flooding, complete wildfire detection, or energy/outage functionality. The existing model limitations and AI-tool/student contribution disclosures are in the README and [CREDITS.md](../CREDITS.md).
