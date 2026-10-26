import { realpathSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

/** A successful Next build must not publish an interface without its forecast API. */
export async function ensureVercelData({ env = process.env, root = repository, run = spawnSync } = {}) {
  // Local/Actions builds keep their explicit export workflow; every build verifies its output.
  if (env.VERCEL === '1' && env.OUTLOOK_API_PREPARED !== '1') {
    console.log('Preparing the published forecast snapshot before the Vercel web build.');
    const result = run('bash', [resolve(root, 'scripts/vercel-git-build.sh'), '--export-only'], {
      cwd: root, env, stdio: 'inherit',
    });
    if (result.error || result.status !== 0) throw new Error('Forecast preparation failed; the incomplete web app will not be built. Check the forecast export logs and repository-root access.');
  }
  let manifest;
  try {
    const api = resolve(root, 'web/public/api');
    const json = async path => JSON.parse(await readFile(resolve(api, path), 'utf8'));
    manifest = await json('build.json');
    const places = await json('places.json');
    if (manifest.schema_version !== 1 || !Array.isArray(places) || !places.length || manifest.places !== places.length)
      throw new Error('Incomplete neighborhood export');
    for (const place of places) {
      if (typeof place.id !== 'string' || !/^[a-z0-9-]+$/.test(place.id)) throw new Error('Invalid neighborhood export');
      await json(`outlook/${place.id}.json`);
    }
    await json('scenarios.json');
    await json('health.json');
  } catch {
    throw new Error('Forecast JSON is missing or incomplete. Use the repository-root vercel.json and the forecast export build; publishing only Next.js leaves the app unable to load.');
  }
  const policy = (env.OUTLOOK_REQUIRE_LIVE_FORECASTS || '0').trim();
  if (!['0', '1'].includes(policy)) throw new Error('OUTLOOK_REQUIRE_LIVE_FORECASTS must be 0 or 1.');
  if (policy === '1' && manifest.forecast_status !== 'ready') throw new Error('No current forecast coverage is available. Refresh the published source state before deploying with OUTLOOK_REQUIRE_LIVE_FORECASTS=1.');
}

if (process.argv[1] && realpathSync(process.argv[1]) === realpathSync(fileURLToPath(import.meta.url))) {
  await ensureVercelData();
}
