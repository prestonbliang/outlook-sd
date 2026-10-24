import type { TileName } from "./api";
import { KINDS, type Summary } from "./community";
export { KINDS, KIND_LABEL } from "./community";
export type { Summary } from "./community";

const URL_ = process.env.NEXT_PUBLIC_SUPABASE_URL?.replace(/\/$/, "");
const ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
export const reportsEnabled = Boolean(URL_ && ANON);
export const REPORTS_CHANGED = "outlook-sd-reports-changed";
export interface Count { place_id: string; hazard: TileName; kind: string; day: string; n: number }

function headers() {
  return { apikey: ANON!, Authorization: `Bearer ${ANON}`, "Content-Type": "application/json" };
}
function clientId(): string {
  // Require a persistent browser code so disabled storage can't silently defeat repeat limits.
  try {
    let id = localStorage.getItem("outlook-sd-client");
    if (!id) { id = crypto.randomUUID(); localStorage.setItem("outlook-sd-client", id); }
    return id;
  } catch {
    throw new Error("Enable site storage in your browser to submit an observation.");
  }
}
export async function sendReport(placeId: string, hazard: TileName, kind: string): Promise<void> {
  if (!reportsEnabled) throw new Error("Community reporting is not connected yet.");
  if (!KINDS[hazard].some((k) => k.kind === kind)) throw new Error("Choose a report type for this hazard.");
  let r: Response;
  try {
    r = await fetch(`${URL_}/rest/v1/reports`, {
      method: "POST", headers: { ...headers(), Prefer: "return=minimal" },
      body: JSON.stringify({ place_id: placeId, hazard, kind, client_id: clientId() }),
      signal: AbortSignal.timeout(15000),
    });
  } catch (e) {
    if (e instanceof Error && e.message.includes("site storage")) throw e;
    throw new Error("Could not send your report. Check your connection and try again.");
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
  const rows = await r.json();
  if (!Array.isArray(rows)) throw new Error("Community observations are temporarily unavailable.");
  return rows;
}
