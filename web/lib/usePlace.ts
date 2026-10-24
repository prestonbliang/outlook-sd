"use client";
import { useCallback, useEffect, useState } from "react";
import type { Place } from "./api";
import { getPlaces } from "./places";

const DEFAULT_PLACE = "downtown";
const KEY = "outlook-sd-place";
const EVENT = "outlook-sd-place-change";
export function usePlace() {
  const [places, setPlaces] = useState<Place[]>([]);
  const [placeId, setPlaceId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt(x => x + 1), []);
  useEffect(() => {
    let active = true;
    let catalogue: Place[] = [];
    function sync() {
      if (!catalogue.length) return;
      let saved: string | null = null;
      try { saved = localStorage.getItem(KEY); } catch { /* storage blocked */ }
      const requested = new URLSearchParams(window.location.search).get("place") || saved || DEFAULT_PLACE;
      const resolved = catalogue.find(p => p.id === requested)?.id ?? catalogue.find(p => p.id === DEFAULT_PLACE)?.id ?? catalogue[0].id;
      const url = new URL(window.location.href);
      if (url.searchParams.get("place") !== resolved) {
        url.searchParams.set("place", resolved);
        window.history.replaceState(window.history.state, "", url);
      }
      try { localStorage.setItem(KEY, resolved); } catch { /* URL still preserves selection without storage. */ }
      setPlaceId(resolved);
    }
    setError(null);
    getPlaces().then(rows => { if (active) { catalogue = rows; setPlaces(rows); sync(); } })
      .catch(e => { if (active) setError(e.message); });
    window.addEventListener("popstate", sync); window.addEventListener(EVENT, sync); window.addEventListener("storage", sync);
    return () => {
      active = false; window.removeEventListener("popstate", sync); window.removeEventListener(EVENT, sync); window.removeEventListener("storage", sync);
    };
  }, [attempt]);
  const choose = useCallback((id: string) => {
    if (!places.some(p => p.id === id)) return;
    try { localStorage.setItem(KEY, id); } catch { /* remember for this page only */ }
    const url = new URL(window.location.href);
    if (url.searchParams.get("place") !== id) {
      url.searchParams.set("place", id); window.history.pushState(null, "", url);
    }
    setPlaceId(id); window.dispatchEvent(new Event(EVENT));
  }, [places]);
  return { places, place: places.find(p => p.id === placeId) ?? null, placeId, choose, error, retry };
}
