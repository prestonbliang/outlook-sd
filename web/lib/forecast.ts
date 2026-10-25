import type { Day, SourceCheck, Tile, TileName } from "./api";

export const FORECAST_ZONE = "America/Los_Angeles";
export function localDate(now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: FORECAST_ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}
export function dateLabel(date: string, now = new Date()): string {
  if (date === localDate(now)) return "Today";
  return new Date(`${date}T12:00:00Z`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: FORECAST_ZONE });
}
export function sourceDateLabel(value: string): string {
  // Timestamped observations use Pacific dates; date-only historical labels retain their source day.
  return /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) && Number.isFinite(Date.parse(value))
    ? new Date(value).toLocaleDateString("en-US", { timeZone: FORECAST_ZONE }) : value.slice(0, 10);
}
export function currentDay(tile: Pick<Tile, "days">, now = new Date()): Day | undefined {
  return tile.days.find(day => day.date === localDate(now) && Number.isFinite(day.value));
}
export function sourceIsCurrent(check: Pick<SourceCheck, "reference_at" | "max_age_hours">, now = Date.now()): boolean {
  if (!check || typeof check !== "object") return false;
  const age = check.reference_at ? now - Date.parse(check.reference_at) : NaN;
  return Number.isFinite(age) && Number.isFinite(check.max_age_hours) && check.max_age_hours > 0
    && age >= -300000 && age <= check.max_age_hours * 3600000;
}
export function advisoryIsCurrent(advisory: Tile["official_advisory"], now = Date.now()): boolean {
  return Boolean(typeof advisory.active === "boolean" && advisory.check && sourceIsCurrent(advisory.check, now)
    && (!advisory.expires_at || Date.parse(advisory.expires_at) > now));
}
export type ForecastState = "current" | "stale" | "unavailable" | "not_applicable";
export function forecastState(tile: Pick<Tile, "days" | "run_ts" | "status" | "stale_inputs" | "source_checks" | "model">, now = Date.now(), date = localDate(new Date(now))): ForecastState {
  if (tile.status === "not_applicable") return "not_applicable";
  if (!tile.days.some(day => day.date === date && Number.isFinite(day.value))) return "unavailable";
  const age = tile.run_ts ? now - Date.parse(tile.run_ts) : NaN;
  const maxAge = tile.model === "calheatscore" ? 26 * 3600000 : 6 * 3600000;
  if (!Number.isFinite(age) || age < -300000 || age > maxAge || tile.stale_inputs.length
    || (tile.source_checks !== undefined && (!Array.isArray(tile.source_checks) || tile.source_checks.some(check => !sourceIsCurrent(check, now))))) return "stale";
  return "current";
}
export function observationIsCurrent(time: string, now = Date.now()): boolean {
  const age = now - Date.parse(time);
  return Number.isFinite(age) && age >= -300000 && age <= 3 * 3600000;
}
export function freshnessLabel(iso: string | null | undefined, now = Date.now()): string {
  const age = iso ? now - Date.parse(iso) : NaN;
  if (!Number.isFinite(age) || age < -300000) return "Update time unavailable";
  if (age < 60000) return "Updated just now";
  if (age < 3600000) return `Updated ${Math.floor(age / 60000)} min ago`;
  if (age < 86400000) return `Updated ${Math.floor(age / 3600000)} hr ago`;
  const days = Math.floor(age / 86400000);
  return `Updated ${days} day${days === 1 ? "" : "s"} ago`;
}

export function forecastDates(now = Date.now(), count = 3): string[] {
  const start = new Date(`${localDate(new Date(now))}T12:00:00Z`);
  return Array.from({ length: count }, (_, i) => {
    const day = new Date(start); day.setUTCDate(start.getUTCDate() + i);
    return day.toISOString().slice(0, 10);
  });
}

export function needsAttention(tile: TileName, level: string | null): boolean {
  return (tile === "air" ? ["usg", "unhealthy", "very_unhealthy", "hazardous"] : ["moderate", "high", "very_high"])
    .includes(level ?? "");
}

export function planningDays(tiles: Tile[], selected: TileName[], now = Date.now()) {
  return forecastDates(now).map(date => {
    const items = [...new Set(selected)].map(hazard => {
      const tile = tiles.find(t => t.tile === hazard);
      const day = tile?.days.find(d => d.date === date && Number.isFinite(d.value));
      const state = tile ? forecastState(tile, now, date) : "unavailable";
      const rated = Boolean(day?.level && ["low", "moderate", "high", "very_high", "good", "usg", "unhealthy", "very_unhealthy", "hazardous"].includes(day.level));
      return { hazard, day, state, rated, attention: state === "current" && needsAttention(hazard, day?.level ?? null) };
    });
    return { date, items, current: items.filter(i => i.state === "current" && i.rated).length,
      attention: items.filter(i => i.attention), incomplete: items.some(i => i.state !== "not_applicable" && (i.state !== "current" || !i.rated)) };
  });
}

export function parseHazardFocus(raw: string | null, supported: readonly TileName[]): TileName[] {
  try {
    const value: unknown = JSON.parse(raw ?? "null");
    if (!Array.isArray(value) || value.some(item => !supported.includes(item))) return [...supported];
    return supported.filter(item => value.includes(item));
  } catch { return [...supported]; }
}
