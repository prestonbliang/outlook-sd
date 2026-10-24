export const API = process.env.NEXT_PUBLIC_API_URL || "/api";
export const PMTILES = process.env.NEXT_PUBLIC_PMTILES_URL || "/tiles/sandiego.pmtiles";
export const TZ = "America/Los_Angeles";

export type TileName = "water" | "air" | "heat" | "flood" | "fire";
export const TILE_ORDER: TileName[] = ["water", "air", "heat", "flood", "fire"];
export const TILE_NAME: Record<TileName, string> = { water: "Water", air: "Air", heat: "Heat", flood: "Flood", fire: "Fire" };

export interface Place { id: string; name: string; zip: string; lat: number; lon: number; coastal: boolean; kind: string }
export interface Day { date: string; level: string | null; value: number | null; verdict: string; [k: string]: unknown }
export interface Factor { label: string; value: string; direction: "up" | "down" }
export interface Tile {
  tile: TileName; days: Day[]; reason: string | null; factors: Factor[]; sources: string[]; stale_inputs: string[];
  verdict?: string; status?: string; unit?: { id: string; name: string }; units?: string; model?: string; run_ts?: string;
  official_advisory: { active: boolean | null; url: string; headline?: string | null };
  current?: { aqi: number; parameter: string; site: string; time: string; level: string; verdict: string };
  active_fires?: { name: string; acres: number; km: number; url: string }[]; red_flag?: string[];
  active_fires_available?: boolean;
}
export interface Outlook { place: { id: string; name: string; zip: string; coastal?: boolean }; updated_at: string | null; tiles: Tile[] }
export interface Series { units: string; threshold: { value: number; label: string } | null; observed_label?: string;
  observed: { t: string; v: number }[]; forecast: { t: string; v: number; hi?: number }[] }
export interface Hazard extends Tile {
  place: Outlook["place"]; window: { verdict: string; through: string } | null; series: Series | null;
  what_to_do: string; metrics: TrackSummary | null;
}
export interface TrackRow { metric: string; model: number | null; model_ci95?: [number, number]; baselines: Record<string, number | null> }
export interface TrackSummary { headline: string; period: string; inputs: string; table: TrackRow[]; note?: string;
  provisional?: boolean; beats_baseline: boolean; replays?: { name: string; issued?: string; note?: string;
  days?: { date: string; observed: number; lvl_q50: number; lvl_q90: number; lvl_tide: number }[] }[] }

export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(`${API}/${path}`, { cache: "no-store", signal });
  if (!r.ok) throw new Error(`Could not load ${path} (HTTP ${r.status})`);
  return r.json();
}

export const LEVEL_WORD: Record<string, string> = {
  low: "Low", moderate: "Moderate", high: "High", very_high: "Very high", good: "Good",
  usg: "Unhealthy for sensitive groups", unhealthy: "Unhealthy", very_unhealthy: "Very unhealthy", hazardous: "Hazardous",
};

export function levelColor(tile: TileName, level: string | null | undefined): string {
  if (!level) return "var(--rule)";
  return `var(--${tile === "air" ? "aqi" : "lvl"}-${level.replace("_", "-")})`;
}

export const dayName = (date: string, style: "short" | "long" = "short") =>
  new Date(`${date}T12:00:00`).toLocaleDateString("en-US", { weekday: style });

export function updatedText(iso: string | null): string {
  if (!iso) return "Not updated yet";
  const d = new Date(iso);
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: TZ }).toLowerCase();
  const day = d.toLocaleDateString("en-US", { weekday: "long", timeZone: TZ });
  return `Updated ${time} ${day}`;
}

export function haversineKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
  const r = Math.PI / 180;
  const h = Math.sin(((b.lat - a.lat) * r) / 2) ** 2 +
    Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(((b.lon - a.lon) * r) / 2) ** 2;
  return 12742 * Math.asin(Math.sqrt(h));
}

/** Same values as styles/tokens.css — MapLibre paint expressions cannot read CSS variables. */
export const LEVEL_HEX: Record<string, string> = {
  low: "#2E8540", moderate: "#E5A000", high: "#D54309", very_high: "#8B1A3A",
};
export const AQI_HEX: Record<string, string> = {
  good: "#00E400", moderate: "#FFFF00", usg: "#FF7E00", unhealthy: "#FF0000", very_unhealthy: "#8F3F97", hazardous: "#7E0023",
};
