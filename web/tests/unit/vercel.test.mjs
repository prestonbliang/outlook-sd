import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { prepare, validateExport } from '../../../scripts/prepare-vercel.mjs';
const tiles = ['water', 'air', 'heat', 'flood', 'fire'];
async function fixture() {
  const root = await mkdtemp(join(tmpdir(), 'outlook-vercel-'));
  const source = join(root, 'out');
  async function put(path, body) {
    await mkdir(join(source, path, '..'), { recursive: true });
    await writeFile(join(source, path), typeof body === 'string' ? body : JSON.stringify(body));
  }
  for (const page of ['index.html', '404.html', 'map/index.html', 'data/index.html', 'track-record/index.html', ...tiles.map(t => `hazard/${t}/index.html`)]) await put(page, '<html>Outlook SD test fixture</html>');
  await put('app-build.json', { schema_version: 1, reporting: 'unconfigured' });
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
  const dates = Array.from({ length: 4 }, (_, k) => new Date(Date.parse(`${today}T12:00:00Z`) + k * 86400000).toISOString().slice(0, 10));
  await put('api/build.json', { schema_version: 1, generated_at: new Date().toISOString(), forecast_date: dates[0], places: 1, forecast_status: 'unavailable' });
  await put('api/places.json', [{ id: 'test-place' }]);
  await put('api/map/dates.json', { dates });
  await put('api/health.json', {}); await put('api/track-record.json', {});
  await put('api/outlook/test-place.json', { place: { id: 'test-place' }, tiles: tiles.map(tile => ({ tile })) });
  for (const tile of tiles) {
    for (const suffix of ['', ...dates.map(d => `-${d}`)]) await put(`api/map/${tile}${suffix}.json`, { type: 'FeatureCollection', features: [] });
    await put(`api/hazard/${tile}/test-place.json`, { tile, place: { id: 'test-place' } });
  }
  await put('tiles/sandiego.pmtiles', 'PMTiles test fixture');
  return { root, source, output: join(root, 'output') };
}

test('live deployment refuses a snapshot without live forecasts', async () => {
  const f = await fixture();
  try { await assert.rejects(validateExport(f.source), /No recent live forecasts/); }
  finally { await rm(f.root, { recursive: true, force: true }); }
});
test('explicit initial launch packages the export with API freshness and page routing', async () => {
  const f = await fixture();
  try {
    await prepare({ ...f, allowUnavailable: true });
    const config = JSON.parse(await readFile(join(f.output, 'config.json'), 'utf8'));
    assert.equal(config.version, 3);
    assert.equal(config.routes.find(r => r.src === '/api/.*').headers['Cache-Control'], 'no-store');
    const security = config.routes.find(r => r.src === '/.*' && r.headers?.['X-Content-Type-Options']).headers;
    assert.equal(security['X-Frame-Options'], 'DENY');
    assert.match(security['Content-Security-Policy'], /frame-ancestors 'none'/);
    assert.match(security['Permissions-Policy'], /geolocation=\(self\)/);
    assert.ok(config.routes.some(r => r.src === '/map/' && r.dest === '/map/index.html'));
    assert.ok(config.routes.some(r => r.src === '/map' && r.status === 308));
    assert.equal(config.routes.at(-1).status, 404);
    assert.ok((await readFile(join(f.output, 'static/index.html'), 'utf8')).includes('Outlook SD'));
  } finally { await rm(f.root, { recursive: true, force: true }); }
});
test('incomplete detail exports cannot deploy', async () => {
  const f = await fixture();
  try {
    await rm(join(f.source, 'api/hazard/water/test-place.json'));
    await assert.rejects(validateExport(f.source, { allowUnavailable: true }), /ENOENT/);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});
test('an old snapshot cannot deploy even for an initial launch', async () => {
  const f = await fixture();
  try {
    const path = join(f.source, 'api/build.json'); const manifest = JSON.parse(await readFile(path, 'utf8'));
    manifest.generated_at = '2020-01-01T00:00:00Z'; await writeFile(path, JSON.stringify(manifest));
    await assert.rejects(validateExport(f.source, { allowUnavailable: true }), /not recent/);
  } finally { await rm(f.root, { recursive: true, force: true }); }
});
test('packaging cannot delete its input directory', async () => {
  const f = await fixture();
  try { await assert.rejects(prepare({ source: f.source, output: f.source, allowUnavailable: true }), /must be separate/); }
  finally { await rm(f.root, { recursive: true, force: true }); }
});

test('test reporting builds require an explicit QA override and cannot be mistaken for a release', async () => {
  const f = await fixture();
  try {
    await writeFile(join(f.source, 'app-build.json'), JSON.stringify({ schema_version: 1, reporting: 'test' }));
    await assert.rejects(validateExport(f.source, { allowUnavailable: true }), /test reporting configuration/);
    await assert.doesNotReject(validateExport(f.source, { allowUnavailable: true, allowTestReporting: true }));
  } finally { await rm(f.root, { recursive: true, force: true }); }
});
