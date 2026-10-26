# Release verification and demo

The v1.0 release is available at https://outlook-sd.vercel.app/. Hourly publishing and the public-site check have passed. See [STATUS.md](STATUS.md) for evidence and [MODELS.md](MODELS.md) for scientific limits. This guide reproduces QA and describes setup for other installations.

## Product scope

Outlook SD helps San Diego residents understand beach water, air, heat, coastal flooding and fire conditions in the neighborhoods they care about. It combines model forecasts, official warning links, an interactive county map, and structured community observations. Reporting blind spots identify where more observations are needed; they never imply safety. Saved places and shared map views make this a repeatable daily workflow.

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

## Deploy another installation

1. Configure Supabase with `supabase/schema.sql` and browser-safe URL/publishable-key values. Existing projects can apply the additive migrations. Use a separate database only when separate observations are intended.
2. Restore the runtime `state` archive or bootstrap genuine source tables with [SETUP.md](SETUP.md). Source data and credentials are not committed; do not retrain the included models merely to deploy.
3. Configure the existing Vercel project and GitHub Actions credentials using [VERCEL.md](VERCEL.md). Set the repository variable `OUTLOOK_PUBLIC_URL` to the public production origin; protected preview URLs require a bypass secret for automated checks.
4. Run the pipeline and inspect source health. Verify the public site with `python scripts/check_deployment.py https://YOUR-PUBLIC-DOMAIN --require-reporting`. Confirm a real, truthful observation when appropriate; do not seed production with QA reports.

Publishing succeeds only after build/package validation and the hosted check. A successful check requires some current forecast coverage; inspect individual hazards for their availability. A first setup with `--allow-unavailable` is not evidence of live forecasts.

## A focused 60-second demonstration

Use the real configured release; check its timestamps and connectivity before recording.

- **0–15 seconds:** Open Today, select Imperial Beach, and explain the five local hazards. Point to the update time and the difference between a forecast and an official advisory. If a forecast is unavailable, say so.
- **15–30 seconds:** Open Map & reports, select a hazard and forecast day, and inspect an area. Explain that flood coverage is approximate and fire levels are relative ranks. Share the view to preserve the selected place/day/hazard.
- **30–45 seconds:** Show recent community coverage and submit one truthful observation for conditions you are actually observing. Explain that reports never alter forecast probabilities and blind spots describe participation. If reporting is not configured, do not present the submission as working.
- **45–60 seconds:** Show a saved neighborhood and the Track record page. Explain one model result and its limitation, then show the Data page's sources and privacy explanation.

The distinctive value is the combination of transparent local forecasts, an inspectable map, and community coverage without inventing a safety score. Avoid claiming perfect accuracy, verified unique people, street-level flooding, complete wildfire detection, or energy/outage functionality. Model limitations are in [MODELS.md](MODELS.md); AI-tool and recorded student contributions are in [CREDITS.md](../CREDITS.md).
