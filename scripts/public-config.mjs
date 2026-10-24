/** Fail before bundling if a private Supabase key is put in public configuration. */
export function validatePublicConfig(env) {
  const url = env.NEXT_PUBLIC_SUPABASE_URL?.trim() ?? '';
  const key = env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim() ?? '';
  if (Boolean(url) !== Boolean(key)) throw new Error('Set both NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY, or leave both unset.');
  if (!url) return;
  const parsed = new URL(url);
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(parsed.hostname);
  if (parsed.username || parsed.password || parsed.search || parsed.hash || parsed.pathname !== '/' || !['http:', 'https:'].includes(parsed.protocol) || (parsed.protocol !== 'https:' && !local))
    throw new Error('The public reporting URL must use HTTPS, or HTTP on localhost for development.');
  let role;
  if (key.split('.').length === 3) {
    try { role = JSON.parse(Buffer.from(key.split('.')[1], 'base64url').toString('utf8')).role; } catch { /* Opaque public test keys are checked by their service. */ }
  }
  if (key.startsWith('sb_secret_') || role === 'service_role') throw new Error('A private Supabase key cannot be bundled in the browser. Use the anon public key.');
}

/** Public release metadata contains configuration state, never credentials. */
export function publicBuildMetadata(env) {
  validatePublicConfig(env);
  const url = env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  if (!url) return { schema_version: 1, reporting: 'unconfigured' };
  const host = new URL(url).hostname;
  const test = host.endsWith('.invalid') || ['localhost', '127.0.0.1', '[::1]'].includes(host)
    || env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim() === 'test-public-key';
  return { schema_version: 1, reporting: test ? 'test' : 'configured' };
}

export function assertReleaseBuild(metadata, { allowTestReporting = false } = {}) {
  if (metadata.schema_version !== 1 || !['configured', 'unconfigured', 'test'].includes(metadata.reporting))
    throw new Error('Build configuration metadata is missing or invalid. Rebuild the site.');
  if (metadata.reporting === 'test' && !allowTestReporting)
    throw new Error('This build uses test reporting configuration. Rebuild with real public settings before deploying.');
}
