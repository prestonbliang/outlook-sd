import { get, type Place } from "./api";
let pending: Promise<Place[]> | undefined;
let loadedAt = 0;
/** Share the static neighborhood catalogue across header, picker, and page hooks. */
export function getPlaces(): Promise<Place[]> {
  if (!pending || Date.now() - loadedAt > 60000) {
    loadedAt = Date.now();
    pending = get<Place[]>("places.json").then(rows => {
      if (!Array.isArray(rows) || !rows.length || rows.some(p => !p || typeof p.id !== "string" || !/^[a-z0-9-]{2,60}$/.test(p.id)
        || typeof p.name !== "string" || !p.name.trim() || typeof p.zip !== "string" || !/^\d{5}$/.test(p.zip)
        || typeof p.coastal !== "boolean" || !Number.isFinite(p.lat) || Math.abs(p.lat) > 90 || !Number.isFinite(p.lon) || Math.abs(p.lon) > 180)
        || new Set(rows.map(p => p.id)).size !== rows.length)
        throw new Error("The neighborhood list is unavailable. Please try again.");
      return rows;
    }).catch(error => { pending = undefined; throw error; });
  }
  return pending;
}
