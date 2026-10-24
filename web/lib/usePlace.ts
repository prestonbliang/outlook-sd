"use client";
import { useCallback, useEffect, useState } from "react";
import { Place, get } from "./api";

const DEFAULT_PLACE = "downtown";
const KEY = "outlook-sd-place";

/** Current place from ?place=…, else the last one picked on this device, else Downtown. */
export function usePlace() {
  const [places, setPlaces] = useState<Place[]>([]);
  const [placeId, setPlaceId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let saved: string | null = null;
    try { saved = localStorage.getItem(KEY); } catch { /* storage blocked */ }
    const requested = new URLSearchParams(window.location.search).get("place") || saved || DEFAULT_PLACE;
    get<Place[]>("places.json", controller.signal).then((rows) => {
      setPlaces(rows);
      setPlaceId(rows.some((p) => p.id === requested) ? requested : DEFAULT_PLACE);
    }).catch((e) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, []);
  const choose = useCallback((id: string) => {
    setPlaceId(id);
    try { localStorage.setItem(KEY, id); } catch { /* storage blocked */ }
    const u = new URL(window.location.href);
    u.searchParams.set("place", id);
    window.history.replaceState(null, "", u);
  }, []);
  const place = places.find((p) => p.id === placeId) ?? null;
  return { places, place, placeId, choose, error };
}
