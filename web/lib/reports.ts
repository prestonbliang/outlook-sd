import type { TileName } from "./api";
import { KINDS, LEGACY_KINDS, parseReportKinds, validateSummaries, type Summary } from "./community";
import { reportingHeaders } from "./reporting-headers";
export { KINDS, KIND_LABEL } from "./community";
export type { Summary } from "./community";

const URL_ = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim().replace(/\/$/, "");
const PUBLIC_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim()
  || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
export const reportsEnabled = Boolean(URL_ && PUBLIC_KEY);
export const REPORTS_CHANGED = "outlook-sd-reports-changed";
export interface Count { place_id: string; hazard: TileName; kind: string; day: string; n: number }

let kindRequest: Promise<string[]> | undefined;
/** Discover the database vocabulary before offering choices it may not accept yet. */
export function availableReportKinds(): Promise<string[]> {
  if (!reportsEnabled) return Promise.resolve([]);
  if (!kindRequest) {
    kindRequest = fetch(`${URL_}/rest/v1/rpc/report_kinds`, {
      method: "POST", headers: headers(), body: "{}", signal: AbortSignal.timeout(15000), cache: "no-store",
    }).then(async response => {
      if (!response.ok) throw new Error("Observation options are unavailable");
      return parseReportKinds(await response.json());
    }).catch(() => {
      // Older databases keep their working original choices. A new page load retries discovery.
      kindRequest = undefined;
      return [...LEGACY_KINDS];
    });
  }
  return kindRequest;
}

function headers() {
  return reportingHeaders(PUBLIC_KEY!);
}
function clientId(): string {
  // Require a persistent browser code so disabled storage can't silently defeat repeat limits.
  try {
    let id = localStorage.getItem("outlook-sd-client");
    if (!id || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
      id = crypto.randomUUID(); localStorage.setItem("outlook-sd-client", id);
    }
    return id;
  } catch {
    throw new Error("Enable site storage in your browser to submit an observation.");
  }
}
export async function sendReport(placeId: string, hazard: TileName, kind: string): Promise<void> {
  if (!reportsEnabled) throw new Error("Community reporting is not connected yet.");
  if (!/^[a-z0-9-]{2,60}$/.test(placeId)) throw new Error("Choose a listed neighborhood.");
  if (!KINDS[hazard]?.some((k) => k.kind === kind)) throw new Error("Choose a report type for this hazard.");
  let r: Response;
  try {
    r = await fetch(`${URL_}/rest/v1/reports`, {
      method: "POST", headers: { ...headers(), Prefer: "return=minimal" },
      body: JSON.stringify({ place_id: placeId, hazard, kind, client_id: clientId() }),
      signal: AbortSignal.timeout(15000),
    });
  } catch (e) {
    if (e instanceof Error && e.message.includes("site storage")) throw e;
    throw new Error("Could not confirm your report was saved. Check your connection and try again.");
  }
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    const known = ["Too many reports from this device", "You already sent this report", "Choose a listed", "Choose a coastal"];
    throw new Error(known.some((s) => String(body.message).startsWith(s))
      ? body.message : "Your report could not be saved. Please try again later.");
  }
  window.dispatchEvent(new Event(REPORTS_CHANGED));
}
export async function reportCounts(days = 7): Promise<Count[]> {
  const r = await fetch(`${URL_}/rest/v1/rpc/report_counts`, {
    method: "POST", headers: headers(), body: JSON.stringify({ days }), signal: AbortSignal.timeout(15000),
  });
  if (!r.ok) throw new Error("Could not load community reports.");
  return r.json();
}
export async function reportSummary(hours = 24, signal?: AbortSignal): Promise<Summary[]> {
  const r = await fetch(`${URL_}/rest/v1/rpc/report_summary`, {
    method: "POST", headers: headers(), body: JSON.stringify({ hours }),
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
    cache: "no-store",
  });
  if (!r.ok) throw new Error("Community observations could not be loaded. Please try again.");
  try { return validateSummaries(await r.json()); }
  catch { throw new Error("Community observations are temporarily unavailable."); }
}
