export interface FlowScenario {
  period: string; samples: number; no_cap_unsafe_share: number;
  caps: { cap_mgd: number; unsafe_share: number }[]; recent_mgd?: number; recent_through?: string;
}
export interface SeaScenario {
  period: string; minor_flood_ft_mllw: number; rises: { rise_ft: number; days_per_year: number }[];
}
export interface Scenarios { flow: FlowScenario | null; sea_level: SeaScenario | null }
const number = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0;
const share = (v: unknown): v is number => number(v) && v <= 1;
export function parseScenarios(value: unknown): Scenarios {
  if (!value || typeof value !== "object") throw new Error("The scenario data could not be read.");
  const raw = value as Partial<Scenarios>;
  const f = raw.flow, s = raw.sea_level;
  const flow = f && typeof f.period === "string" && Number.isSafeInteger(f.samples) && f.samples > 0
    && share(f.no_cap_unsafe_share) && Array.isArray(f.caps) && f.caps.length
    && f.caps.every(c => c && number(c.cap_mgd) && share(c.unsafe_share))
    && new Set(f.caps.map(c => c.cap_mgd)).size === f.caps.length
    ? { ...f, caps: [...f.caps].sort((a, b) => a.cap_mgd - b.cap_mgd) } : null;
  const sea_level = s && typeof s.period === "string" && Number.isFinite(s.minor_flood_ft_mllw)
    && Array.isArray(s.rises) && s.rises.some(r => r?.rise_ft === 0)
    && s.rises.every(r => r && number(r.rise_ft) && number(r.days_per_year) && r.days_per_year <= 366)
    && new Set(s.rises.map(r => r.rise_ft)).size === s.rises.length
    ? { ...s, rises: [...s.rises].sort((a, b) => a.rise_ft - b.rise_ft) } : null;
  return { flow, sea_level };
}
/** Zero stays zero; a counterfactual above the baseline still fits its chart. */
export function comparisonWidth(value: number, ...values: number[]): number {
  const maximum = Math.max(0, value, ...values);
  return maximum === 0 ? 0 : Math.max(0, Math.min(100, value / maximum * 100));
}
export function scenarioStep(values: number[]): number {
  return values.length < 2 ? 1 : Math.min(...values.slice(1).map((v, i) => v - values[i]));
}
