import assert from 'node:assert/strict';
import { test } from 'node:test';
import { reportingHeaders } from '../../lib/reporting-headers.ts';

test('publishable keys authenticate anonymous reporting without an invalid bearer JWT', () => {
  const headers = reportingHeaders('sb_publishable_browser_test_key');
  assert.equal(headers.apikey, 'sb_publishable_browser_test_key');
  assert.equal(headers['Content-Type'], 'application/json');
  assert.equal(Object.hasOwn(headers, 'Authorization'), false);
});

test('legacy anon keys retain their existing authentication headers', () => {
  const headers = reportingHeaders('legacy.anon.jwt');
  assert.equal(headers.apikey, 'legacy.anon.jwt');
  assert.equal(headers.Authorization, 'Bearer legacy.anon.jwt');
});
