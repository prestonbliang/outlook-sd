/** Publishable keys are opaque API keys, not bearer JWTs. Keep legacy anon keys working. */
export function reportingHeaders(key: string): Record<string, string> {
  return {
    apikey: key,
    "Content-Type": "application/json",
    ...(key.startsWith("sb_publishable_") ? {} : { Authorization: `Bearer ${key}` }),
  };
}
