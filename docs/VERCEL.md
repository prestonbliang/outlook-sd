# Launch on Vercel

Outlook SD uses Vercel to serve a static Next.js export. GitHub Actions runs the Python forecasting job, preserves its SQLite log in the `state` release, and publishes a tested snapshot. Supabase handles community observations directly from the browser.

The deploy scripts use Vercel's [Build Output API](https://vercel.com/docs/build-output-api) and [`deploy --prebuilt`](https://vercel.com/docs/cli/deploy). The prepared `.vercel/output` contains only the built site, with explicit page routing and cache rules. The Python datasets and private API keys are never uploaded as public files.

## 1. Link the existing Vercel project

Use the existing Outlook SD project. Do not create a second project just to deploy from this repository.

In Vercel, find the project ID and the account/team ID in Settings. Create a deployment token with access to that project. Configure these **GitHub repository Actions secrets**:

| Secret | Purpose |
| --- | --- |
| `VERCEL_TOKEN` | Authenticate the Vercel CLI |
| `VERCEL_ORG_ID` | Existing account/team ID |
| `VERCEL_PROJECT_ID` | Existing Outlook SD project ID |
| `NEXT_PUBLIC_SUPABASE_URL` | Reporting project URL, embedded at build time |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Reporting public key, embedded at build time |
| `AIRNOW_API_KEY` | Live air observations and forecasts |
| `FIRMS_MAP_KEY` | Satellite fire detections |
| `VERCEL_AUTOMATION_BYPASS_SECRET` | Optional: let the read-only check access protected previews |

Use the anon public key for reporting, never a Supabase service-role key. Apply `supabase/schema.sql` to that project first. A Vercel-only environment variable does not automatically become available to a build performed in GitHub Actions; configure the public settings in Actions as well.

Keep Vercel's project Root Directory at the repository root for this CLI deployment path. The Python pipeline belongs in GitHub Actions. Avoid parallel Git-based production deployments that build directly from source without the generated forecast API: use the workflow below as the release path for this architecture.

## 2. Run repository checks

The `checks` workflow runs Python regressions, generates API files without historical data, builds the frontend, checks TypeScript, validates the Vercel package, and runs Playwright with a mocked reporting endpoint. It does not deploy its test build.

Merge a validated code change before starting the hourly production job. A static prebuilt deployment is the exact output of the tested build, so public environment values must be present before `npm run build`.

## 3. First launch before forecast state exists

Open Actions → **deploy-vercel** → Run workflow:

- Target: `preview`.
- Enable `allow_unavailable` only if you deliberately want the first site to display unavailable forecasts while data is being configured.

This path creates the map/neighborhood interface and supports reporting when Supabase is configured. It does not invent live forecasts. The default launch refuses a snapshot without recent forecasts.

The workflow prints the deployment URL in its summary, then checks the pages, JSON API, and a 16-byte PMTiles range request. An initial deployment to a brand-new Vercel project can become its first production deployment even when `--prod` is omitted, as described in the CLI documentation. Reuse the existing project and inspect the target in the dashboard.

## 4. Supply the live pipeline state

No `state` release was available in the repository when this deployment phase began. To generate one, follow [SETUP.md](SETUP.md) to download the source tables, obtain the ACS population data, perform a live run, and package/upload `state.tar.gz` to the release tagged `state`.

If the original working app has a state archive elsewhere, restore that archive rather than retraining the included models. The code repository alone does not contain its runtime state. The recent IBWC export remains a separate manual source-data dependency; keep the water evaluation provisional until a new evaluation is completed.

Once state exists, run **deploy-vercel** with `allow_unavailable` disabled. It refreshes sources, persists the forecast log, exports JSON, tests/builds the frontend, prepares Vercel output, deploys, and checks the hosted result. Switch the target to `production` when publishing the live snapshot.

## 5. Hourly updates

The existing `hourly-pipeline` workflow uses the same prebuilt package and deployment check. It requires saved state and refuses an export with no recent forecasts. Manual and hourly deployments share a concurrency group so they cannot overwrite the state archive concurrently.

API responses use `Cache-Control: no-store`; versioned Next assets use long caching. The basemap is a static PMTiles file whose HTTP range support is checked after deployment. Unknown page paths return the static 404 page rather than falling back to the home page.

## Local equivalents

```bash
make build
cd web
npm run typecheck
npm run test:unit
npx playwright install chromium
npm run test:e2e
cd ..
node scripts/prepare-vercel.mjs
scripts/deploy-vercel.sh preview
python scripts/check_deployment.py https://YOUR-DEPLOYMENT.vercel.app
```

For an explicit first launch, append `--allow-unavailable` to both packaging and deployment checking. Set the three Vercel environment variables locally before deploying; do not commit tokens or paste them into documentation.
