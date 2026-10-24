import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fetchJSON } from '../../lib/request.ts';

test('temporary server failures retry exactly once', async () => {
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => ++calls === 1 ? new Response('', { status: 503 }) : Response.json({ ok: true });
  try { assert.deepEqual(await fetchJSON('https://test.invalid'), { ok: true }); assert.equal(calls, 2); }
  finally { globalThis.fetch = original; }
});
test('missing data is not retried or exposed as a raw storage filename', async () => {
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => { calls++; return new Response('', { status: 404 }); };
  try { await assert.rejects(fetchJSON('https://test.invalid/private-path.json'), /not available yet/); assert.equal(calls, 1); }
  finally { globalThis.fetch = original; }
});
test('cancelled navigation never issues a fetch', async () => {
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({}); };
  const controller = new AbortController(); controller.abort();
  try { await assert.rejects(fetchJSON('https://test.invalid', { signal: controller.signal })); assert.equal(calls, 0); }
  finally { globalThis.fetch = original; }
});
test('an HTML error page cannot masquerade as JSON', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response('<html>error</html>');
  try { await assert.rejects(fetchJSON('https://test.invalid'), /unreadable response/); }
  finally { globalThis.fetch = original; }
});
test('write requests are never automatically retried', async () => {
  const original = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => { calls++; return new Response('', { status: 503 }); };
  try { await assert.rejects(fetchJSON('https://test.invalid', { method: 'POST' })); assert.equal(calls, 1); }
  finally { globalThis.fetch = original; }
});
