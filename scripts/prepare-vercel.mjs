// Package the tested static export using Vercel's Build Output API v3.
import { cp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { assertReleaseBuild } from './public-config.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const TILES = ['water', 'air', 'heat', 'flood', 'fire'];
const escapeRegex = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const json = async (path) => JSON.parse(await readFile(path, 'utf8'));

export async function validateExport(source, { allowUnavailable = false, allowTestReporting = false, now = new Date() } = {}) {
  for (const page of ['index.html', '404.html', 'map/index.html', 'data/index.html', 'track-record/index.html',
    ...TILES.map(t => `hazard/${t}/index.html`)]) {
    if (!(await readFile(join(source, page), 'utf8')).trim()) throw new Error(`Missing exported page: ${page}`);
  }
  assertReleaseBuild(await json(join(source, 'app-build.json')), { allowTestReporting });
  const manifest = await json(join(source, 'api/build.json'));
  if (manifest.schema_version !== 1) throw new Error('Unsupported snapshot manifest');
  const age = now.getTime() - Date.parse(manifest.generated_at);
  if (!Number.isFinite(age) || age < -300000 || age > 6 * 3600000) throw new Error('Export is not recent; regenerate the API and rebuild');
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit', day: '2-digit' }).format(now);
  if (manifest.forecast_date !== today) throw new Error('Snapshot is for a previous forecast day; regenerate the API and rebuild');
  if (!allowUnavailable && manifest.forecast_status !== 'ready') {
    throw new Error('No recent live forecasts. Restore/bootstrap source state, or explicitly use --allow-unavailable for an initial launch');
  }
  const places = await json(join(source, 'api/places.json'));
  if (!places.length || places.length !== manifest.places) throw new Error('Neighborhood manifest does not match exported places');
  const { dates } = await json(join(source, 'api/map/dates.json'));
  if (dates?.length !== 4 || new Set(dates).size !== 4 || dates[0] !== manifest.forecast_date) throw new Error('Forecast map dates do not match the snapshot');
  await json(join(source, 'api/health.json'));
  await json(join(source, 'api/track-record.json'));
  for (const tile of TILES) {
    for (const suffix of ['', ...dates.map(d => `-${d}`)]) {
      const layer = await json(join(source, `api/map/${tile}${suffix}.json`));
      if (layer.type !== 'FeatureCollection' || !Array.isArray(layer.features)) throw new Error(`Invalid ${tile} map layer`);
    }
  }
  for (const place of places) {
    const outlook = await json(join(source, `api/outlook/${place.id}.json`));
    if (outlook.place.id !== place.id || TILES.some(t => !outlook.tiles.some(x => x.tile === t))) throw new Error(`Incomplete outlook: ${place.id}`);
    for (const tile of TILES) {
      const detail = await json(join(source, `api/hazard/${tile}/${place.id}.json`));
      if (detail.place.id !== place.id || detail.tile !== tile) throw new Error(`Incomplete detail: ${place.id}/${tile}`);
    }
  }
  const basemap = await readFile(join(source, 'tiles/sandiego.pmtiles'));
  if (basemap.subarray(0, 7).toString() !== 'PMTiles') throw new Error('San Diego basemap is missing or invalid');
  return manifest;
}

async function pagesUnder(dir, prefix = '') {
  const pages = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const name = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) pages.push(...await pagesUnder(join(dir, entry.name), name));
    else if (entry.name === 'index.html') pages.push(name);
  }
  return pages;
}

export async function prepare({ source = join(ROOT, 'web/out'), output = join(ROOT, '.vercel/output'), services = false, ...options } = {}) {
  source = resolve(source); output = resolve(output);
  // Packaging must never delete a source tree, even when called from another script.
  if (source === output || source.startsWith(`${output}/`) || output.startsWith(`${source}/`)) throw new Error('Source and output directories must be separate');
  const manifest = await validateExport(source, options);
  const routes = [
    { src: '/api/.*', headers: { 'Cache-Control': 'no-store' }, continue: true },
    { src: '/_next/static/.*', headers: { 'Cache-Control': 'public, max-age=31536000, immutable' }, continue: true },
    { src: '/tiles/.*', headers: { 'Cache-Control': 'public, max-age=86400' }, continue: true },
    { src: '/.*', headers: {
      'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'strict-origin-when-cross-origin',
      'X-Frame-Options': 'DENY', 'Content-Security-Policy': "frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
      'Permissions-Policy': 'camera=(), microphone=(), geolocation=(self)',
    }, continue: true },
    { handle: 'filesystem' },
  ];
  for (const page of await pagesUnder(source)) {
    const directory = page.slice(0, -'index.html'.length);
    if (directory) routes.push({ src: `/${escapeRegex(directory.slice(0, -1))}`, headers: { Location: `/${directory}` }, status: 308 });
    routes.push({ src: `/${escapeRegex(directory)}`, dest: `/${page}` });
  }
  routes.push({ src: '/.*', dest: '/404.html', status: 404 });
  await rm(output, { recursive: true, force: true });
  await mkdir(output, { recursive: true });
  const webOutput = services ? join(output, 'services/web') : output;
  await mkdir(webOutput, { recursive: true });
  await cp(source, join(webOutput, 'static'), { recursive: true });
  await writeFile(join(webOutput, 'config.json'), JSON.stringify({ version: 3, routes,
    overrides: { 'tiles/sandiego.pmtiles': { contentType: 'application/vnd.pmtiles' } } }, null, 2) + '\n');
  if (services) await writeFile(join(output, 'config.json'), JSON.stringify({ version: 3,
    services: [{ name: 'web', root: 'web' }], routes: [{ src: '/.*', destination: { service: 'web' } }] }, null, 2) + '\n');
  return manifest;
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try {
    const unknown = process.argv.slice(2).filter(a => !['--allow-unavailable', '--allow-test-reporting'].includes(a));
    if (unknown.length) throw new Error(`Unknown arguments: ${unknown.join(' ')}`);
    const manifest = await prepare({ services: true, allowUnavailable: process.argv.includes('--allow-unavailable'), allowTestReporting: process.argv.includes('--allow-test-reporting') });
    process.stdout.write(`Vercel package ready: ${manifest.places} neighborhoods; forecasts ${manifest.forecast_status}\n`);
  } catch (error) { process.stderr.write(`${error.message}\n`); process.exitCode = 1; }
}
