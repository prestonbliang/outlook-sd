import assert from 'node:assert/strict';
import { test } from 'node:test';
import { advisoryIsCurrent, currentDay, forecastDates, forecastState, parseHazardFocus, planningDays, sourceDateLabel } from '../../lib/forecast.ts';

const now = Date.parse('2026-10-24T18:00:00Z');
const tile = (hazard, level = 'low') => ({ tile: hazard, days: [{ date: '2026-10-24', value: 1, level }], run_ts: new Date(now).toISOString(), stale_inputs: [] });
test('individual sources expire before an otherwise recent forecast', () => {
  const t = { ...tile('heat'), source_checks: [{ reference_at: new Date(now).toISOString(), max_age_hours: 1 }] };
  assert.equal(forecastState(t, now), 'current');
  assert.equal(forecastState(t, now + 2 * 3600000), 'stale');
  assert.equal(forecastState({ ...t, source_checks: [null] }, now), 'stale');
});
test('missing and nonfinite values never become current', () => {
  for (const value of [undefined, null, NaN, Infinity, true]) {
    const t = { ...tile('heat'), days: [{ date: '2026-10-24', value }] };
    assert.equal(currentDay(t, new Date(now)), undefined);
    assert.equal(forecastState(t, now), 'unavailable');
  }
});
test('planning keeps stale high ratings and missing coverage out of attention counts', () => {
  const plan = planningDays([tile('heat', 'high'), { ...tile('fire', 'high'), stale_inputs: ['Weather'] }], ['heat', 'fire', 'water'], now)[0];
  assert.equal(plan.current, 1);
  assert.deepEqual(plan.attention.map(i => i.hazard), ['heat']);
  assert.equal(plan.incomplete, true);
  assert.equal(plan.items.find(i => i.hazard === 'water').state, 'unavailable');
});
test('an unrated value is not an all-clear planning day', () => {
  const plan = planningDays([tile('heat', null)], ['heat'], now)[0];
  assert.equal(plan.current, 0);
  assert.equal(plan.incomplete, true);
});
test('air attention begins at sensitive-group levels, while moderate heat counts', () => {
  const plan = planningDays([tile('air', 'moderate'), tile('heat', 'moderate')], ['air', 'heat'], now)[0];
  assert.deepEqual(plan.attention.map(i => i.hazard), ['heat']);
});
test('planning calendar days cross daylight saving without repeats or UTC drift', () => {
  assert.deepEqual(forecastDates(Date.parse('2026-11-01T01:00:00Z')), ['2026-10-31', '2026-11-01', '2026-11-02']);
});
test('source timestamps use Pacific dates without shifting date-only historical records', () => {
  assert.equal(sourceDateLabel('2026-10-25T01:00:00+00:00'), '10/24/2026');
  assert.equal(sourceDateLabel('2026-03-04 00:00:00'), '2026-03-04');
});
test('focus preferences reject corrupt or unknown entries and preserve deliberate empty selections', () => {
  const ids = ['water', 'air', 'heat', 'flood', 'fire'];
  assert.deepEqual(parseHazardFocus('invalid', ids), ids);
  assert.deepEqual(parseHazardFocus('["heat","../bad"]', ids), ids);
  assert.deepEqual(parseHazardFocus('["heat","heat"]', ids), ['heat']);
  assert.deepEqual(parseHazardFocus('[]', ids), []);
});
test('official alerts need both a current feed check and an unexpired alert', () => {
  const advisory = { active: true, check: { reference_at: new Date(now).toISOString(), max_age_hours: 3 }, expires_at: new Date(now + 3600000).toISOString() };
  assert.equal(advisoryIsCurrent(advisory, now), true);
  assert.equal(advisoryIsCurrent(advisory, now + 2 * 3600000), false);
  assert.equal(advisoryIsCurrent({ active: false }, now), false);
  assert.equal(advisoryIsCurrent({ ...advisory, active: null }, now), false);
});
