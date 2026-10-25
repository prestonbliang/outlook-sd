import assert from 'node:assert/strict';
import { test } from 'node:test';
import { comparisonWidth, parseScenarios } from '../../lib/scenarios.ts';
const flow = { period: 'Historical', samples: 10, no_cap_unsafe_share: 0, caps: [{ cap_mgd: 0, unsafe_share: 0 }] };
test('zero-baseline charts stay finite and zero remains visually zero', () => {
  assert.equal(comparisonWidth(0, 0), 0);
  assert.equal(comparisonWidth(30, 20, 30), 100);
  assert.ok(comparisonWidth(20, 20, 30) < 100);
  assert.ok(parseScenarios({ flow, sea_level: null }).flow);
});
test('invalid scenarios are unavailable while valid independent sections remain usable', () => {
  const result = parseScenarios({ flow, sea_level: { period: 'x', minor_flood_ft_mllw: 7, rises: [null] } });
  assert.ok(result.flow); assert.equal(result.sea_level, null);
  assert.equal(parseScenarios({ flow: { ...flow, no_cap_unsafe_share: 2 } }).flow, null);
  assert.deepEqual(parseScenarios({ flow: null, sea_level: null }), { flow: null, sea_level: null });
});
