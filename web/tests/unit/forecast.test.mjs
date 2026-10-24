import assert from 'node:assert/strict';
import { test } from 'node:test';
import { currentDay, dateLabel, forecastState, freshnessLabel, localDate, observationIsCurrent } from '../../lib/forecast.ts';
import { parseWatchlist } from '../../lib/watchlist.ts';

const now = new Date('2026-10-24T01:30:00Z'); // Still Oct 23 in San Diego.
const tile = { days: [{ date: '2026-10-23', value: 1 }], run_ts: now.toISOString(), stale_inputs: [] };
test('forecast dates follow San Diego regardless of UTC date', () => {
  assert.equal(localDate(now), '2026-10-23');
  assert.equal(dateLabel('2026-10-23', now), 'Today');
  assert.match(dateLabel('2026-10-24', now), /Sat/);
});
test('a future-only forecast cannot be presented as today', () => {
  const future = { ...tile, days: [{ date: '2026-10-24', value: 1 }] };
  assert.equal(currentDay(future, now), undefined);
  assert.equal(forecastState(future, +now), 'unavailable');
  assert.equal(forecastState(future, +now, '2026-10-24'), 'current');
});
test('freshness distinguishes current, stale, missing, and inapplicable data', () => {
  assert.equal(forecastState(tile, +now), 'current');
  assert.equal(forecastState({ ...tile, run_ts: '2026-10-23T12:00:00Z' }, +now), 'stale');
  assert.equal(forecastState({ ...tile, stale_inputs: ['weather'] }, +now), 'stale');
  assert.equal(forecastState({ ...tile, run_ts: 'bad date' }, +now), 'stale');
  assert.equal(forecastState({ ...tile, days: [{ date: '2026-10-23', value: null }] }, +now), 'unavailable');
  assert.equal(forecastState({ ...tile, status: 'not_applicable' }, +now), 'not_applicable');
});
test('daily state forecasts have a daily freshness window', () => {
  assert.equal(forecastState({ ...tile, model: 'calheatscore', run_ts: '2026-10-23T07:00:00Z' }, +now), 'current');
});
test('stale observations never claim to be current', () => {
  assert.equal(observationIsCurrent(now.toISOString(), +now), true);
  assert.equal(observationIsCurrent('2026-10-23T12:00:00Z', +now), false);
  assert.equal(observationIsCurrent('invalid', +now), false);
  assert.equal(freshnessLabel(null, +now), 'Update time unavailable');
  assert.equal(freshnessLabel('2026-10-22T01:30:00Z', +now), 'Updated 2 days ago');
});
test('saved places reject corrupt storage, duplicate IDs, and unlimited growth', () => {
  assert.deepEqual(parseWatchlist('not json'), []);
  assert.deepEqual(parseWatchlist('{"id":"alpine"}'), []);
  assert.deepEqual(parseWatchlist('["la-jolla","la-jolla",5,"../private"]'), ['la-jolla']);
  assert.equal(parseWatchlist(JSON.stringify(Array.from({ length: 12 }, (_, i) => `place-${i}`))).length, 8);
});
