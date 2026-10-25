#!/usr/bin/env bash
# Vercel runs this from the web service; all Python work is build-time only.
set -euo pipefail
cd "$(dirname "$0")/.."

if command -v uv >/dev/null 2>&1; then
  outlook_uv="$(command -v uv)"
else
  # Frontend build images need not have uv installed. Bootstrap it without changing system Python.
  outlook_bootstrap="$(mktemp -d "${TMPDIR:-/tmp}/outlook-uv.XXXXXX")"
  trap 'rm -rf "$outlook_bootstrap"' EXIT
  python3 -m venv "$outlook_bootstrap"
  "$outlook_bootstrap/bin/python" -m pip install --disable-pip-version-check 'uv==0.13.5'
  outlook_uv="$outlook_bootstrap/bin/uv"
fi

"$outlook_uv" sync --frozen --python 3.12
"$outlook_uv" run --frozen python scripts/vercel_state.py --published
"$outlook_uv" run --frozen python -m api.export
npm --prefix web run build

# Reuse the same completeness/freshness/private-key checks as the hourly release.
node --input-type=module <<'JS'
import { existsSync } from 'node:fs';
import { validateExport } from './scripts/prepare-vercel.mjs';
if (existsSync('.env')) process.loadEnvFile('.env');
const policy = (process.env.OUTLOOK_REQUIRE_LIVE_FORECASTS || '0').trim();
if (!['0', '1'].includes(policy)) throw new Error('OUTLOOK_REQUIRE_LIVE_FORECASTS must be 0 or 1.');
const requireLive = policy === '1';
const manifest = await validateExport('web/out', { allowUnavailable: !requireLive });
console.log(`Git build verified: ${manifest.places} neighborhoods; forecasts ${manifest.forecast_status}`);
if (manifest.forecast_status !== 'ready') console.log('No current forecasts: the site will display explicit unavailable states. Configure runtime state before a live forecast launch.');
JS
