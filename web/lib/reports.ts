import { TileName } from "./api";

/** Community reports (Supabase). The anon key is public by design: the table only accepts inserts and exposes
 *  daily counts through report_counts(); raw rows and device IDs are never readable (see supabase/schema.sql). */
const URL_ = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ANON = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
export const reportsEnabled = Boolean(URL_ && ANON);

export interface Kind { kind: string; label: string; problem: boolean }
export const KINDS: Record<TileName, Kind[]> = {
  water: [{ kind: "water_sewage", label: "Sewage smell or brown water", problem: true },
          { kind: "water_sign", label: "Closure or warning sign posted", problem: true },
          { kind: "water_ok", label: "Water looked and smelled fine", problem: false }],
  air: [{ kind: "air_smoke", label: "Smoke, haze or ash", problem: true },
        { kind: "air_ok", label: "Air seemed clear", problem: false }],
  heat: [{ kind: "heat_extreme", label: "Dangerously hot", problem: true },
         { kind: "heat_ok", label: "Comfortable", problem: false }],
  flood: [{ kind: "flood_street", label: "Water on a street or parking lot", problem: true },
          { kind: "flood_overtop", label: "Waves or tide over a seawall or path", problem: true },
          { kind: "flood_ok", label: "No flooding", problem: false }],
  fire: [{ kind: "fire_smoke", label: "Smoke from a fire nearby", problem: true },
         { kind: "fire_ok", label: "No smoke", problem: false }],
};
export const KIND_LABEL: Record<string, string> = Object.fromEntries(
  Object.values(KINDS).flat().map((k) => [k.kind, k.label]));

export interface Count { place_id: string; hazard: TileName; kind: string; day: string; n: number }

function headers() {
  return { apikey: ANON!, Authorization: `Bearer ${ANON}`, "Content-Type": "application/json" };
}

function clientId(): string {
  try {
    let id = localStorage.getItem("outlook-sd-client");
    if (!id) { id = crypto.randomUUID(); localStorage.setItem("outlook-sd-client", id); }
    return id;
  } catch {
    return crypto.randomUUID(); // storage blocked: rate limits then apply per page load only
  }
}

export async function sendReport(placeId: string, hazard: TileName, kind: string): Promise<void> {
  const r = await fetch(`${URL_}/rest/v1/reports`, {
    method: "POST", headers: { ...headers(), Prefer: "return=minimal" },
    body: JSON.stringify({ place_id: placeId, hazard, kind, client_id: clientId() }),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.message || `Report not sent (HTTP ${r.status})`);
  }
}

export async function reportCounts(days = 7): Promise<Count[]> {
  const r = await fetch(`${URL_}/rest/v1/rpc/report_counts`, { method: "POST", headers: headers(), body: JSON.stringify({ days }) });
  if (!r.ok) throw new Error(`Could not load reports (HTTP ${r.status})`);
  return r.json();
}
