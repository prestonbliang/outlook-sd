# Deploy Outlook SD on Vercel

The root [`vercel.json`](../vercel.json) supports Vercel's GitHub integration and its Services project detection. It explicitly declares **one deployable service**, `web`, rooted in `web/`. This follows Vercel's current [Services configuration](https://vercel.com/docs/services); a single service is supported.

## Architecture

| Component | Location | Runs where |
| --- | --- | --- |
| Next.js 16 / React frontend | `web/`, `web/package.json` | Vercel, as a static export |
| Forecast API assembly | `api/main.py`, `api/export.py` | Build time; emits `web/public/api/*.json` |
| Models, source ingestion, SQLite forecast/score log | `models/`, `pipeline/`, `data/` | Hourly GitHub Actions job with persisted state |
| Community reports and coverage RPCs | `supabase/schema.sql`, browser `web/lib/reports.ts` | Supabase PostgreSQL/PostgREST |
| Basemap, fonts, sprites, map worker | `web/public/`, asset-copy scripts | Static files on Vercel |

The browser already requests static URLs such as `/api/places.json`, `/api/outlook/imperial-beach.json` and `/api/map/heat.json`. These are served by the **web service**, not rewritten into Python endpoints. Reports go directly to Supabase using its publishable or legacy anon key and database policies. There are no Next API route handlers, websocket services, or authenticated application servers to provision.

## Service calls and bindings

The confirmed deployment retains the existing static architecture. The service name is `web`, all public paths route to it, and its explicit `bindings: []` declares that it calls no internal Vercel service.

| Caller | Target | How it is called | Vercel binding |
| --- | --- | --- | --- |
| Browser | `web` | Same-origin `/api/*.json`, page and asset requests | None; public HTTP |
| Web build | Python API assembly | `python -m api.export` invokes FastAPI in-process through TestClient | None; build-time execution |
| Browser | Supabase | `NEXT_PUBLIC_SUPABASE_URL` with the publishable or legacy anon key | None; external managed service |
| GitHub Actions | Source APIs | Scheduled ingestion using provider credentials | None; external providers |

The `localhost:8000` development API command is for local inspection; the deployed frontend does not call it. No Docker/service-discovery hostnames or runtime server-to-server API URLs are used by the web app. `NEXT_PUBLIC_API_URL` remains `/api` by default, so client requests agree with the public paths.

Do not add an unused FastAPI service or manually configure a binding URL for this architecture. Vercel [service bindings](https://vercel.com/docs/services/bindings) are injected only into runtime functions, not static browser code or build steps. A future private runtime API would require a server-side caller and a deliberate architecture change.

For routing checks, run `vercel dev --local` (the older `-L` spelling is deprecated). Pages and `/api/*.json` must resolve through `web`, unknown paths return 404, and PMTiles range requests return 206. The local CLI can also serve existing repository source paths from its development filesystem; this is not the production asset allowlist. Inspect the production build output separately: it must contain the static web assets and exported JSON, with no Python source or SQLite database.

The Python API reads precomputed source tables and SQLite. Its mutable database and the hourly ingestion/inference process must not be placed in request-time Vercel Functions. They remain in GitHub Actions. Do not add `api/main.py` as a second Vercel service. Vercel CLI's warning that the root `api/` directory is not built is expected: its code generates the static JSON during the web build.

## Vercel project settings

Connect the maintained repository (`prestonbliang/outlook-sd` for the fork) to the existing Vercel project:

| Setting | Value |
| --- | --- |
| Root Directory | Repository root (`.`); **not** `web` |
| Project framework | Services / repository configuration |
| Service name | `web` |
| Service framework/root | `nextjs` / `web` (defined in `vercel.json`) |
| Node.js | `22.x` (also pinned in `web/package.json`) |
| Service Install Command | `npm ci` (defined in configuration) |
| Service Build Command | `bash ../scripts/vercel-git-build.sh` (defined in configuration) |
| Output Directory override | Leave unset/automatic |
| Production branch | Match the branch used by the hourly workflow; normally the repository default branch |

Remove old root-level build/install/output overrides or an old FastAPI service configuration from the dashboard. Build/runtime settings belong to the configured web service. Do not set Output Directory to `out`: with the Next.js framework integration, Vercel first reads Next's internal `.next` manifests, recognizes `output: "export"`, and then publishes `web/out` itself. An `out` override makes the Next builder look for `out/routes-manifest.json`, which does not exist.

The top-level catch-all rewrite delegates to the web service while preserving the requested path. It is **not** an SPA rewrite to `/index.html`: exported pages retain their routes, API URLs return JSON, unknown paths return 404, and assets retain their file paths. JSON uses `Cache-Control: no-store`; hashed Next assets use immutable caching; security headers preserve geolocation for this origin. Vercel serves PMTiles with normal HTTP byte-range support.

No Vercel token or project/team IDs are required as application environment variables for the GitHub integration. The integration handles deployment authorization.

## Environment variables

Set the following in Vercel's Environment Variables UI for the environments where each feature should work. Values are never committed.

| Variable | Needed for | Visibility |
| --- | --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | Community reports; set together with the key below | Public, embedded in the browser build |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Community reports; use the browser-safe `sb_publishable_...` key | Public by design; RLS restricts access |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Optional legacy fallback; the publishable key takes precedence | Public by design; never use a service-role or secret key |
| `OUTLOOK_STATE_URL` | Optional archive override; otherwise prefer the deploying repository's public `state` release, then upstream if its asset is missing | Build-only; a signed URL must remain secret |
| `OUTLOOK_REQUIRE_LIVE_FORECASTS` | Set `1` for a live production release; fails builds without current forecast coverage | Build-only; default `0` permits an initial unavailable-data launch |
| `NEXT_PUBLIC_API_URL` | Optional; default `/api` already points at the generated JSON | Public |
| `NEXT_PUBLIC_PMTILES_URL` | Optional; default `/tiles/sandiego.pmtiles` | Public |

With the Supabase URL and both key options unset, the app explicitly says reporting is disconnected and does not present a working submission form. Configure the URL and one browser-safe key. A partial configuration or private key in either public key variable fails the build, even if the other key takes precedence. Publishable keys are sent only as `apikey`, not as bearer JWTs; legacy anon keys retain their existing authentication. Reserved test-reporting endpoints also fail the Git deployment build. Rebuild after changing public environment variables.

The separate **GitHub Actions** pipeline needs `AIRNOW_API_KEY`, `FIRMS_MAP_KEY`, both Supabase public values, and a `NWS_USER_AGENT` repository variable containing a project contact. Source API keys are not needed on Vercel: the Git build exports existing predictions and never runs ingestion/training. The CLI/hourly publishing workflows additionally need GitHub Actions secrets `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`, and optionally `VERCEL_AUTOMATION_BYPASS_SECRET` for protected-preview checks.

## What the Git build does

1. `npm ci` installs the web dependencies.
2. `scripts/vercel-git-build.sh` uses uv, or bootstraps pinned uv into an isolated temporary Python environment if the frontend build image does not have it. It installs the frozen Python dependencies using Python 3.12.
3. The build script calls `scripts/vercel_state.py --published`. An explicit `OUTLOOK_STATE_URL` always takes precedence. Otherwise `VERCEL_GIT_REPO_OWNER` and `VERCEL_GIT_REPO_SLUG` select the deploying repository's `state/state.tar.gz` release asset. Only a missing asset (HTTP 404) falls back to `https://github.com/raunavm/outlook-sd/releases/download/state/state.tar.gz`; authentication, server and corrupt-archive failures fail the build. If system Git variables are disabled, the shared upstream asset is used directly; set the explicit fork URL to select its archive in that case. Release assets are not included in Git checkouts or copied into forks. Restoration permits only ordinary files under `data/processed/` and `data/outlook.db`, rejects links, traversal/source-code paths and oversized archives, and never prints signed URLs.
4. `python -m api.export` generates the neighborhood, hazard, map, scenario and health JSON through the existing API contracts. It does not create sample forecasts or user reports.
5. `npm --prefix web run build` copies local map assets and produces the Next.js static export.
6. The existing release validator checks complete pages, neighborhood/hazard/date JSON, map data, basemap bytes, build configuration, and freshness. `OUTLOOK_REQUIRE_LIVE_FORECASTS=1` requires current real forecast coverage.

Running the restorer directly without `--published` or `OUTLOOK_STATE_URL` keeps local data and performs no download. Freshness and unavailable states still apply when a pipeline stops updating. The fork's real runtime archive was bootstrapped on October 25, 2026; this does not configure hourly Vercel publishing. See [SETUP.md](SETUP.md) to bootstrap actual data. Never run `make train` simply to deploy the committed models.

For a public GitHub repository with a populated `state` release, its asset URL can be used as `OUTLOOK_STATE_URL`. A private repository's release asset needs a genuinely accessible signed/private-storage download URL: Vercel's GitHub checkout permission does not automatically authenticate arbitrary archive downloads. Keep the archive current through the existing pipeline. The URL is a build input, not something the browser fetches.

## Hourly forecasts and existing prebuilt deployments

### Protection against an incomplete standalone web build

`web`'s ordinary `npm run build` now detects Vercel and prepares the published source state and Python API export before running Next.js. This also covers an existing dashboard configured to build the web package directly. The repository-root build marks its already-completed export to avoid duplicate preparation; both paths verify the required JSON exists. Preparation failures stop the build instead of publishing a frontend whose `/api/places.json` returns 404. Local and GitHub Actions builds keep their explicit export workflow. The recommended project Root Directory remains the repository root so all configuration and route/security headers apply.

Environment variables belong to each Vercel project separately. Configuring Supabase on `outlook-sd-kof2` does not configure `outlook-sd`; both projects need their own Production/Preview public values if both are maintained. A Vercel success status alone is not a functional check: run the hosted checker against the exact domain users will open.

A GitHub push rebuilds code, not hourly weather data. Keep the `hourly-pipeline` workflow enabled once its `state` release is available. It restores state, fetches sources, performs inference/logging/scoring, exports API JSON, builds/tests the site, and publishes the snapshot to the **same Vercel project**.

The CLI packager uses the documented [Build Output API](https://vercel.com/docs/build-output-api/primitives): static files are emitted directly under `.vercel/output/static/`, with standard string destinations in `.vercel/output/config.json`. The root `vercel.json` still declares the web service for Git builds; its Services configuration is not a prebuilt artifact format. Nesting files under `output/services/web` leaves no root static files for the CLI to serve. The deployment guard rejects this unsupported layout as well as test reporting builds.

Set the **GitHub repository variable** `OUTLOOK_PUBLIC_URL` to the existing public production origin (for example `https://outlook-sd.vercel.app`). Production workflows check that domain, because generated Vercel deployment URLs may require login even when the production domain is public. Checks compare the published source commit and snapshot generation time with the local build, so an older healthy deployment cannot produce a false success. Preview checks still use their generated URL and require `VERCEL_AUTOMATION_BYPASS_SECRET` when protected. Do not disable deployment protection to make a check pass.

For code-triggered production builds, set `OUTLOOK_STATE_URL` to the latest accessible state and `OUTLOOK_REQUIRE_LIVE_FORECASTS=1` after bootstrapping. This prevents a code push without usable state from replacing a live forecast deployment with unavailable data. Keep the Vercel production branch aligned with the workflow checkout branch.

## Verification and local commands

Run from the repository root, with web dependencies installed:

```bash
bash scripts/vercel-git-build.sh
cd web
npm run typecheck
npm run test:unit
cd ..
node scripts/prepare-vercel.mjs --allow-unavailable
```

`--allow-unavailable` is only for an intentional first launch; omit it for a live prebuilt release. For actual CLI publishing, set its three deployment credentials and use `scripts/deploy-vercel.sh preview`. A preview for a new project may become its initial production deployment, so verify the target in the Vercel dashboard.

After deploying through GitHub, run the read-only hosted check:

```bash
python scripts/check_deployment.py https://YOUR-DEPLOYMENT.vercel.app --allow-unavailable
```

Omit `--allow-unavailable` for the real forecast launch. The check verifies pages, JSON, snapshot freshness, 110 neighborhoods, and a 16-byte PMTiles range response. Then test a real report against the configured Supabase project.

Add `--require-reporting` once community observations are intended to be live. It fails if the deployed browser build still reports unconfigured/test settings, even when the database is working separately. The hosted check also verifies the What-if page and scenario JSON and rechecks forecast expiry at request time. Inspect **Data → What is connected?** for publication provenance and the separate live community-read status.

## Remaining operational requirements

The repository's runtime archive, forecast database, source credentials and hosted Supabase schema are not supplied by `vercel.json`. Configure those before claiming live forecasts/reporting. Dashboard settings were not changed during this improvement pass; pushing code can trigger the existing Git integration. Local build and packaging checks alone do not establish that a hosted project has the right credentials or archive access. See [STATUS.md](STATUS.md) for executed hosted checks and outstanding operational work.
