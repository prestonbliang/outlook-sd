import assert from 'node:assert/strict';
import { test } from 'node:test';
import { KINDS, coverageFor, reportAge } from '../../lib/community.ts';

test('repeat observations from one browser never meet the coverage goal', () => {
  assert.equal(coverageFor({ total: 100, reporters: 1 }), 'limited');
  assert.equal(coverageFor({ total: 3, reporters: 3 }), 'reported');
  assert.equal(coverageFor({ total: 2, reporters: 2 }), 'limited');
});
test('empty coverage is a reporting gap, not an all-clear', () => {
  assert.equal(coverageFor(), 'none');
  assert.equal(coverageFor({ total: 0, reporters: 0 }), 'none');
});
test('observation labels and problem flags align with the database vocabulary', () => {
  const seen = new Set();
  for (const [hazard, kinds] of Object.entries(KINDS)) {
    assert.ok(kinds.some(k => !k.problem));
    for (const kind of kinds) {
      assert.ok(kind.kind.startsWith(`${hazard}_`));
      assert.equal(kind.problem, !kind.kind.endsWith('_ok'));
      assert.ok(!seen.has(kind.kind)); seen.add(kind.kind);
    }
  }
});
test('freshness handles old, invalid, and future times without implying negative ages', () => {
  const now = Date.parse('2026-10-24T12:00:00Z');
  assert.equal(reportAge('2026-10-24T11:59:30Z', now), 'Just now');
  assert.equal(reportAge('2026-10-24T11:30:00Z', now), '30 min ago');
  assert.equal(reportAge('2026-10-24T09:00:00Z', now), '3 hr ago');
  assert.equal(reportAge('2026-10-22T12:00:00Z', now), '2 days ago');
  assert.equal(reportAge('2026-10-24T13:00:00Z', now), 'Time unavailable');
  assert.equal(reportAge('invalid', now), 'Time unavailable');
});

test('malformed server counts stay unavailable instead of becoming coverage', async () => {
  const { validateSummaries } = await import('../../lib/community.ts');
  const summary = { place_id: 'la-jolla', hazard: 'water', total: 1, reporters: 1, problem_reports: 1, clear_reports: 0,
    last_report_at: '2026-10-24T12:00:00Z', kinds: { water_sewage: 1 } };
  assert.deepEqual(validateSummaries([summary]), [summary]);
  assert.throws(() => validateSummaries([{ ...summary, reporters: '3' }]));
  assert.throws(() => validateSummaries([{ ...summary, total: 10 }]));
  assert.throws(() => validateSummaries([{ ...summary, kinds: { fire_smoke: 1 } }]));
  assert.throws(() => validateSummaries([summary, summary]));
});
