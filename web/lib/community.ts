import type { TileName } from "./api";

export interface Kind { kind: string; label: string; problem: boolean }
export const KINDS: Record<TileName, Kind[]> = {
  water: [{ kind: "water_sewage", label: "Sewage smell or brown water", problem: true },
    { kind: "water_sign", label: "Closure or warning sign posted", problem: true },
    { kind: "water_ok", label: "Water looked and smelled fine", problem: false }],
  air: [{ kind: "air_smoke", label: "Smoke, haze or ash", problem: true },
    { kind: "air_ok", label: "Air seemed clear", problem: false }],
  heat: [{ kind: "heat_extreme", label: "Uncomfortably hot", problem: true },
    { kind: "heat_ok", label: "Comfortable", problem: false }],
  flood: [{ kind: "flood_street", label: "Water on a street or parking lot", problem: true },
    { kind: "flood_overtop", label: "Waves or tide over a seawall or path", problem: true },
    { kind: "flood_ok", label: "No flooding observed", problem: false }],
  fire: [{ kind: "fire_smoke", label: "Smoke from a fire nearby", problem: true },
    { kind: "fire_ok", label: "No smoke observed", problem: false }],
};
export const KIND_LABEL: Record<string, string> = Object.fromEntries(
  Object.values(KINDS).flat().map((k) => [k.kind, k.label]));

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
