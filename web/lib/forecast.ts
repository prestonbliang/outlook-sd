import type { Day, Tile } from "./api";

export const FORECAST_ZONE = "America/Los_Angeles";
export function localDate(now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: FORECAST_ZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}
export function dateLabel(date: string, now = new Date()): string {
  if (date === localDate(now)) return "Today";
  return new Date(`${date}T12:00:00Z`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: FORECAST_ZONE });
}
export function currentDay(tile: Pick<Tile, "days">, now = new Date()): Day | undefined {
  return tile.days.find(day => day.date === localDate(now) && day.value !== null);
}
export type ForecastState = "current" | "stale" | "unavailable" | "not_applicable";
export function forecastState(tile: Pick<Tile, "days" | "run_ts" | "status" | "stale_inputs" | "model">, now = Date.now(), date = localDate(new Date(now))): ForecastState {
  if (tile.status === "not_applicable") return "not_applicable";
  if (!tile.days.some(day => day.date === date && day.value !== null)) return "unavailable";
  const age = tile.run_ts ? now - Date.parse(tile.run_ts) : NaN;
  const maxAge = tile.model === "calheatscore" ? 26 * 3600000 : 6 * 3600000;
  if (!Number.isFinite(age) || age < -300000 || age > maxAge || tile.stale_inputs.length) return "stale";
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
