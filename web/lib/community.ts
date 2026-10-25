import type { TileName } from "./api";

export interface Kind { kind: string; label: string; problem: boolean }
export const KINDS: Record<TileName, Kind[]> = {
  water: [{ kind: "water_sewage", label: "Sewage smell or brown water", problem: true },
    { kind: "water_sign", label: "Closure or warning sign posted", problem: true },
    { kind: "water_debris", label: "Floating litter or debris", problem: true },
    { kind: "water_foam", label: "Unusual foam on the water", problem: true },
    { kind: "water_oily", label: "Oily sheen on the water", problem: true },
    { kind: "water_ok", label: "Water looked and smelled fine", problem: false }],
  air: [{ kind: "air_smoke", label: "Smoke, haze or ash", problem: true },
    { kind: "air_dust", label: "Visible airborne dust", problem: true },
    { kind: "air_odor", label: "Strong or unusual outdoor odor", problem: true },
    { kind: "air_ash", label: "Ash falling from the sky", problem: true },
    { kind: "air_ok", label: "Air seemed clear", problem: false }],
  heat: [{ kind: "heat_extreme", label: "Uncomfortably hot", problem: true },
    { kind: "heat_shade", label: "Little or no shade nearby", problem: true },
    { kind: "heat_cooling", label: "Cooling place closed or inaccessible", problem: true },
    { kind: "heat_night", label: "Still unusually hot after sunset", problem: true },
    { kind: "heat_ok", label: "Comfortable", problem: false }],
  flood: [{ kind: "flood_street", label: "Water on a street or parking lot", problem: true },
    { kind: "flood_overtop", label: "Waves or tide over a seawall or path", problem: true },
    { kind: "flood_path", label: "Flooded sidewalk or walking path", problem: true },
    { kind: "flood_drain", label: "Water pooling around a drain", problem: true },
    { kind: "flood_road", label: "Road blocked by flooding", problem: true },
    { kind: "flood_ok", label: "No flooding observed", problem: false }],
  fire: [{ kind: "fire_smoke", label: "Smoke from a fire nearby", problem: true },
    { kind: "fire_ash", label: "Ash falling nearby", problem: true },
    { kind: "fire_flames", label: "Visible flames near vegetation", problem: true },
    { kind: "fire_closure", label: "Fire-related road or trail closure", problem: true },
    { kind: "fire_ok", label: "No smoke observed", problem: false }],
};
// Databases without the additive options migration still accept this original vocabulary.
export const LEGACY_KINDS = ["water_sewage", "water_sign", "water_ok", "air_smoke", "air_ok", "heat_extreme", "heat_ok",
  "flood_street", "flood_overtop", "flood_ok", "fire_smoke", "fire_ok"];
export function parseReportKinds(value: unknown): string[] {
  if (!Array.isArray(value) || !value.length || value.some(v => typeof v !== "string") || new Set(value).size !== value.length
    || LEGACY_KINDS.some(kind => !value.includes(kind)))
    throw new Error("Observation options could not be read.");
  // Future server options can be ignored until the client knows their labels and classification.
  return Object.values(KINDS).flat().filter(k => value.includes(k.kind)).map(k => k.kind);
}
export const KIND_LABEL: Record<string, string> = Object.fromEntries(
  Object.values(KINDS).flat().map((k) => [k.kind, k.label]));

const OBSERVATION_PHRASES: Record<string, string> = {
  water_sewage: "sewage smell or discolored water", water_sign: "posted closure or warning signs",
  water_debris: "floating litter or debris", water_foam: "unusual foam", water_oily: "an oily sheen",
  air_smoke: "smoke, haze or ash", air_dust: "airborne dust", air_odor: "unusual outdoor odors", air_ash: "falling ash",
  heat_extreme: "uncomfortable heat", heat_shade: "limited shade", heat_cooling: "closed or inaccessible cooling places",
  heat_night: "unusual heat after sunset", flood_street: "water on streets or parking lots",
  flood_overtop: "waves or tides overtopping seawalls or paths", flood_path: "flooded walking paths",
  flood_drain: "water pooling around drains", flood_road: "roads blocked by flooding",
  fire_smoke: "smoke from a nearby fire", fire_ash: "falling ash", fire_flames: "flames near vegetation",
  fire_closure: "fire-related road or trail closures",
};
/** A deterministic account of submitted choices, never a forecast or a safety verdict. */
export function summarizeObservations(summary: Summary) {
  const concerns = KINDS[summary.hazard].filter(k => k.problem && summary.kinds[k.kind] > 0)
    .sort((a, b) => summary.kinds[b.kind] - summary.kinds[a.kind])
    .map(k => OBSERVATION_PHRASES[k.kind]);
  const list = concerns.length < 2 ? concerns.join("") : `${concerns.slice(0, -1).join(", ")} and ${concerns.at(-1)}`;
  const mixed = summary.problem_reports > 0 && summary.clear_reports > 0;
  return {
    headline: mixed ? "Observations are mixed" : concerns.length ? "Reported concerns" : "No concerns noted in these reports",
    detail: concerns.length ? `Recent reports mention ${list}.${mixed
      ? " Other submissions describe no concern. Conditions may differ by location or time; these reports do not establish which account is correct." : ""}`
      : "Participating browsers reported no concern at the time of their observations. This does not establish safe conditions or replace official guidance.",
    evidence: summary.reporters === 1 ? "Only one browser has contributed. Multiple choices from it are not independent confirmation."
      : `${summary.reporters} browser codes contributed. These are not verified people or independent witnesses.`,
  };
}

export interface Summary {
  place_id: string; hazard: TileName; total: number; reporters: number;
  problem_reports: number; clear_reports: number; last_report_at: string; kinds: Record<string, number>;
}
export type Coverage = "none" | "limited" | "reported";
export const COVERAGE_LABEL: Record<Coverage, string> = {
  none: "No recent reports", limited: "More reports needed", reported: "Recent observations",
};
// Three browsers is a participation goal, never a confidence or safety score.
export function coverageFor(summary?: Summary): Coverage {
  if (!summary || summary.total === 0 || summary.reporters === 0) return "none";
  return summary.reporters < 3 ? "limited" : "reported";
}
export function reportAge(iso: string, now = Date.now()): string {
  const age = now - Date.parse(iso);
  if (!Number.isFinite(age) || age < -300000) return "Time unavailable";
  const minutes = Math.max(0, Math.floor(age / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} hr ago`;
  const days = Math.floor(minutes / 1440);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

/** Reject malformed summaries instead of turning corrupt/unavailable data into reporting gaps. */
export function validateSummaries(rows: unknown): Summary[] {
  if (!Array.isArray(rows)) throw new Error("Invalid community observations");
  const seen = new Set<string>();
  for (const row of rows) {
    if (!row || typeof row !== "object" || !/^[a-z0-9-]{2,60}$/.test(row.place_id) || !Object.hasOwn(KINDS, row.hazard)) throw new Error("Invalid community observations");
    const counts = [row.total, row.reporters, row.problem_reports, row.clear_reports];
    if (counts.some(n => !Number.isSafeInteger(n) || n < 0) || row.reporters > row.total || row.total !== row.problem_reports + row.clear_reports || (row.total > 0 && !row.reporters)) throw new Error("Invalid observation counts");
    if (typeof row.last_report_at !== "string" || !/^\d{4}-\d{2}-\d{2}T/.test(row.last_report_at) || !Number.isFinite(Date.parse(row.last_report_at)) || !row.kinds || typeof row.kinds !== "object" || Array.isArray(row.kinds)) throw new Error("Invalid observation details");
    const allowed = KINDS[row.hazard as TileName].map(k => k.kind);
    let total = 0;
    let problems = 0;
    for (const [kind, n] of Object.entries(row.kinds)) {
      if (!allowed.includes(kind) || typeof n !== "number" || !Number.isSafeInteger(n) || n < 0) throw new Error("Invalid observation details");
      total += n;
      if (KINDS[row.hazard as TileName].find(k => k.kind === kind)!.problem) problems += n;
    }
    const key = `${row.place_id}/${row.hazard}`;
    if (total !== row.total || problems !== row.problem_reports || seen.has(key)) throw new Error("Inconsistent community observations");
    seen.add(key);
  }
  return rows;
}
