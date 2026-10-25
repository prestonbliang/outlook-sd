import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ensureVercelData } from '../../scripts/ensure-vercel-data.mjs';

async function snapshot(root) {
  const api = join(root, 'web/public/api');
  await mkdir(join(api, 'outlook'), { recursive: true });
  for (const [path, value] of Object.entries({
    'build.json': { schema_version: 1, places: 1 }, 'places.json': [{ id: 'downtown' }],
    'outlook/downtown.json': { place: { id: 'downtown' }, tiles: [] },
    'health.json': {}, 'scenarios.json': { flow: null, sea_level: null },
  })) await writeFile(join(api, path), JSON.stringify(value));
}
async function temporary(check) {
  const root = await mkdtemp(join(tmpdir(), 'outlook-web-build-'));
  try { await check(root); } finally { await rm(root, { recursive: true, force: true }); }
}

test('local builds require their explicit export without downloading or replacing source data', async () => temporary(async root => {
  const options = { root, env: {}, run: () => assert.fail('Unexpected data preparation') };
  await assert.rejects(ensureVercelData(options), /JSON is missing or incomplete/);
  await snapshot(root);
  await ensureVercelData(options);
}));
test('a standalone Vercel npm build prepares real API export before continuing', async () => temporary(async root => {
  await snapshot(root);
  let calls = 0;
  await ensureVercelData({ root, env: { VERCEL: '1' }, run: (command, args, options) => {
    calls++;
    assert.equal(command, 'bash'); assert.equal(args[1], '--export-only'); assert.equal(options.cwd, root);
    return { status: 0 };
  } });
  assert.equal(calls, 1);
}));
test('root builds avoid duplicate preparation and still verify the export', async () => temporary(async root => {
  const options = { root, env: { VERCEL: '1', OUTLOOK_API_PREPARED: '1' }, run: () => assert.fail('Recursive preparation') };
  await assert.rejects(ensureVercelData(options), /JSON is missing or incomplete/);
  await snapshot(root);
  await ensureVercelData(options);
}));
test('preparation failures cannot silently publish the frontend shell', async () => temporary(async root => {
  await assert.rejects(ensureVercelData({ root, env: { VERCEL: '1' }, run: () => ({ status: 1 }) }), /preparation failed/);
  await assert.rejects(ensureVercelData({ root, env: { VERCEL: '1' }, run: () => ({ status: 0 }) }), /JSON is missing or incomplete/);
}));
test('standalone builds preserve the explicit live-forecast release policy', async () => temporary(async root => {
  await snapshot(root);
  await assert.rejects(ensureVercelData({ root, env: { VERCEL: '1', OUTLOOK_API_PREPARED: '1', OUTLOOK_REQUIRE_LIVE_FORECASTS: '1' } }), /No current forecast coverage/);
}));
