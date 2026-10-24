export function parseWatchlist(value: string | null): string[] {
  try {
    const parsed: unknown = JSON.parse(value ?? "[]");
    return Array.isArray(parsed) ? [...new Set(parsed.filter((id): id is string => typeof id === "string" && /^[a-z0-9-]{2,60}$/.test(id)))].slice(0, 8) : [];
  } catch { return []; }
}
