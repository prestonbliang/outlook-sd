import assert from 'node:assert/strict';
import { test } from 'node:test';
import { assertReleaseBuild, publicBuildMetadata, validatePublicConfig } from '../../../scripts/public-config.mjs';
const url = 'https://project.supabase.co';
test('partial reporting configuration fails explicitly', () => {
  assert.throws(() => validatePublicConfig({ NEXT_PUBLIC_SUPABASE_URL: url }), /Set both/);
  assert.doesNotThrow(() => validatePublicConfig({}));
});
test('service-role and secret keys cannot reach the browser build', () => {
  const jwt = `header.${Buffer.from(JSON.stringify({ role: 'service_role' })).toString('base64url')}.signature`;
  for (const name of ['NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY', 'NEXT_PUBLIC_SUPABASE_ANON_KEY']) {
    for (const key of [jwt, 'sb_secret_test']) assert.throws(() => validatePublicConfig({ NEXT_PUBLIC_SUPABASE_URL: url, [name]: key }), /private Supabase key/);
  }
  assert.throws(() => validatePublicConfig({ NEXT_PUBLIC_SUPABASE_URL: url, NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_test', NEXT_PUBLIC_SUPABASE_ANON_KEY: 'sb_secret_unused' }), /private Supabase key/);
});
test('publishable keys configure reporting without requiring a legacy key', () => {
  const config = { NEXT_PUBLIC_SUPABASE_URL: url, NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'sb_publishable_test' };
  assert.doesNotThrow(() => validatePublicConfig(config));
  assert.deepEqual(publicBuildMetadata(config), { schema_version: 1, reporting: 'configured' });
  assert.ok(!JSON.stringify(publicBuildMetadata(config)).includes(config.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY));
  assert.deepEqual(publicBuildMetadata({ ...config, NEXT_PUBLIC_SUPABASE_ANON_KEY: 'test-public-key' }), { schema_version: 1, reporting: 'configured' });
});
test('remote reporting requires HTTPS but local development remains supported', () => {
  const config = { NEXT_PUBLIC_SUPABASE_URL: 'http://example.com', NEXT_PUBLIC_SUPABASE_ANON_KEY: 'public' };
  assert.throws(() => validatePublicConfig(config), /HTTPS/);
  assert.doesNotThrow(() => validatePublicConfig({ ...config, NEXT_PUBLIC_SUPABASE_URL: 'http://localhost:54321' }));
});

test('release metadata carries no keys and test builds are rejected for deployment', () => {
  const metadata = publicBuildMetadata({ NEXT_PUBLIC_SUPABASE_URL: 'https://reports.example.invalid', NEXT_PUBLIC_SUPABASE_ANON_KEY: 'test-public-key' });
  assert.deepEqual(metadata, { schema_version: 1, reporting: 'test' });
  assert.throws(() => assertReleaseBuild(metadata), /test reporting configuration/);
  assert.doesNotThrow(() => assertReleaseBuild(publicBuildMetadata({})));
  assert.throws(() => assertReleaseBuild({ schema_version: 1, reporting: 'unknown' }), /invalid/);
});
