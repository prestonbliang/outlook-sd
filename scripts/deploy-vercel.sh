#!/usr/bin/env bash
# Publish a prepared Build Output API directory to the configured Vercel project.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${VERCEL_TOKEN:?Set VERCEL_TOKEN in GitHub Actions secrets or your local environment}"
: "${VERCEL_ORG_ID:?Set VERCEL_ORG_ID for the existing Vercel team/account}"
: "${VERCEL_PROJECT_ID:?Set VERCEL_PROJECT_ID for the existing Outlook SD project}"
if [[ ! -f .vercel/output/config.json ]]; then
  echo 'Run node scripts/prepare-vercel.mjs after building the site.' >&2
  exit 1
fi
case "${1:-preview}" in
  preview) deploy_flags=() ;;
  production) deploy_flags=(--prod) ;;
  *) echo 'usage: scripts/deploy-vercel.sh preview|production' >&2; exit 2 ;;
esac
# IDs link the existing project. This file is ignored by git and contains no token.
node --input-type=module <<'JS'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { assertReleaseBuild } from './scripts/public-config.mjs';
const output = JSON.parse(readFileSync('.vercel/output/config.json', 'utf8'));
if (output.version !== 3 || output.services || !existsSync('.vercel/output/static/index.html')) {
  throw new Error('Invalid prebuilt layout: package root static/index.html with scripts/prepare-vercel.mjs before deploying.');
}
assertReleaseBuild(JSON.parse(readFileSync('.vercel/output/static/app-build.json', 'utf8')));
mkdirSync('.vercel', { recursive: true });
writeFileSync('.vercel/project.json', JSON.stringify({
  projectId: process.env.VERCEL_PROJECT_ID, orgId: process.env.VERCEL_ORG_ID,
}));
JS
npx --yes vercel@65.2.0 deploy --prebuilt --yes --token "$VERCEL_TOKEN" "${deploy_flags[@]}"
