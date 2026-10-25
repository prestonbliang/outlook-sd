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

The browser already requests static URLs such as `/api/places.json`, `/api/outlook/imperial-beach.json` and `/api/map/heat.json`. These are served by the **web service**, not rewritten into Python endpoints. Reports go directly to Supabase using its public anon key and database policies. There are no Next API route handlers, websocket services, or authenticated application servers to provision.

## Service calls and bindings

The confirmed deployment retains the existing static architecture. The service name is `web`, all public paths route to it, and its explicit `bindings: []` declares that it calls no internal Vercel service.

| Caller | Target | How it is called | Vercel binding |
| --- | --- | --- | --- |
| Browser | `web` | Same-origin `/api/*.json`, page and asset requests | None; public HTTP |
| Web build | Python API assembly | `python -m api.export` invokes FastAPI in-process through TestClient | None; build-time execution |
| Browser | Supabase | `NEXT_PUBLIC_SUPABASE_URL` with the public anon key | None; external managed service |
| GitHub Actions | Source APIs | Scheduled ingestion using provider credentials | None; external providers |

The `localhost:8000` development API command is for local inspection; the deployed frontend does not call it. No Docker/service-discovery hostnames or runtime server-to-server API URLs are used by the web app. `NEXT_PUBLIC_API_URL` remains `/api` by default, so client requests agree with the public paths.

Do not add an unused FastAPI service or manually configure a binding URL for this architecture. Vercel [service bindings](https://vercel.com/docs/services/bindings) are injected only into runtime functions, not static browser code or build steps. A future private runtime API would require a server-side caller and a deliberate architecture change.

For routing checks, run `vercel dev --local` (the older `-L` spelling is deprecated). Pages and `/api/*.json` must resolve through `web`, unknown paths return 404, and PMTiles range requests return 206. The local CLI can also serve existing repository source paths from its development filesystem; this is not the production asset allowlist. Inspect the production build output separately: it must contain the static web assets and exported JSON, with no Python source or SQLite database.

The Python API reads precomputed source tables and SQLite. Its mutable database and the hourly ingestion/inference process must not be placed in request-time Vercel Functions. They remain in GitHub Actions. Do not add `api/main.py` as a second Vercel service. Vercel CLI's warning that the root `api/` directory is not built is expected: its code generates the static JSON during the web build.

## Vercel project settings

Connect `raunavm/outlook-sd` to the existing Vercel project:

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
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Community reports; use the anon/public key, never service-role or secret keys | Public by design; RLS restricts access |
| `OUTLOOK_STATE_URL` | Optional override for the published forecast archive; Vercel defaults to the upstream public `state` release | Build-only; a signed URL must remain secret |
| `OUTLOOK_REQUIRE_LIVE_FORECASTS` | Set `1` for a live production release; fails builds without current forecast coverage | Build-only; default `0` permits an initial unavailable-data launch |
| `NEXT_PUBLIC_API_URL` | Optional; default `/api` already points at the generated JSON | Public |
| `NEXT_PUBLIC_PMTILES_URL` | Optional; default `/tiles/sandiego.pmtiles` | Public |

With both Supabase values unset, the app explicitly says reporting is disconnected and does not present a working submission form. A partial configuration or private Supabase key fails the build. Reserved test-reporting endpoints also fail the Git deployment build. Rebuild after changing public environment variables.

The separate **GitHub Actions** pipeline needs `AIRNOW_API_KEY`, `FIRMS_MAP_KEY`, both Supabase public values, and a `NWS_USER_AGENT` repository variable containing a project contact. Source API keys are not needed on Vercel: the Git build exports existing predictions and never runs ingestion/training. The CLI/hourly publishing workflows additionally need GitHub Actions secrets `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`, and optionally `VERCEL_AUTOMATION_BYPASS_SECRET` for protected-preview checks.

## What the Git build does

1. `npm ci` installs the web dependencies.
2. `scripts/vercel-git-build.sh` uses uv, or bootstraps pinned uv into an isolated temporary Python environment if the frontend build image does not have it. It installs the frozen Python dependencies using Python 3.12.
3. The build script calls `scripts/vercel_state.py --published`, downloading `OUTLOOK_STATE_URL` or defaulting to `https://github.com/raunavm/outlook-sd/releases/download/state/state.tar.gz`. This explicit build option works even if system environment variables are disabled in the dashboard. This is the project's real published snapshot: release assets are not part of Git checkouts and are not copied into forks. It restores only ordinary files under `data/processed/` and `data/outlook.db`, rejects links, traversal/source-code paths, oversized archives and failed downloads, and never prints signed URLs. A download failure fails the build instead of silently publishing empty forecasts. An explicit URL always takes precedence.
4. `python -m api.export` generates the neighborhood, hazard, map, scenario and health JSON through the existing API contracts. It does not create sample forecasts or user reports.
5. `npm --prefix web run build` copies local map assets and produces the Next.js static export.
6. The existing release validator checks complete pages, neighborhood/hazard/date JSON, map data, basemap bytes, build configuration, and freshness. `OUTLOOK_REQUIRE_LIVE_FORECASTS=1` requires current real forecast coverage.

Running the restorer directly without `--published` or `OUTLOOK_STATE_URL` keeps local data and performs no download. The Vercel build script restores the public upstream snapshot automatically, including when run locally; a fork does not need to duplicate its release to show the same forecasts. Freshness and unavailable states still apply when the upstream pipeline stops updating. For an independently operated fork, supply its own maintained archive URL. See [SETUP.md](SETUP.md) to bootstrap actual data. Never run `make train` simply to deploy the committed models.

For a public GitHub repository with a populated `state` release, its asset URL can be used as `OUTLOOK_STATE_URL`. A private repository's release asset needs a genuinely accessible signed/private-storage download URL: Vercel's GitHub checkout permission does not automatically authenticate arbitrary archive downloads. Keep the archive current through the existing pipeline. The URL is a build input, not something the browser fetches.

## Hourly forecasts and existing prebuilt deployments

A GitHub push rebuilds code, not hourly weather data. Keep the `hourly-pipeline` workflow enabled once its `state` release is available. It restores state, fetches sources, performs inference/logging/scoring, exports API JSON, builds/tests the site, and publishes the snapshot to the **same Vercel project**.

The CLI packager now emits the web service under `.vercel/output/services/web/` with a top-level service route, matching the Git integration. The deployment guard reads service build metadata and still rejects test reporting builds. Manual `deploy-vercel` and hourly workflows remain supported without deploying Python as a server.

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

## Remaining operational requirements

The repository's runtime archive, forecast database, source credentials and hosted Supabase schema are not supplied by `vercel.json`. Configure those before claiming live forecasts/reporting. No hosted Vercel deployment or dashboard setting was changed during this implementation. The local build and packaging checks do not establish that a hosted project has the right credentials or archive access.
