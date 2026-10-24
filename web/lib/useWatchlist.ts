"use client";
import { useCallback, useEffect, useState } from "react";
import { parseWatchlist } from "./watchlist";
const KEY = "outlook-sd-watchlist";
const EVENT = "outlook-sd-watchlist-change";
export function useWatchlist() {
  const [ids, setIds] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    function sync() { try { setIds(parseWatchlist(localStorage.getItem(KEY))); } catch { /* Keep session choices when storage is blocked. */ } }
    sync(); window.addEventListener("storage", sync); window.addEventListener(EVENT, sync);
    return () => { window.removeEventListener("storage", sync); window.removeEventListener(EVENT, sync); };
  }, []);
  const toggle = useCallback((id: string) => {
    if (!/^[a-z0-9-]{2,60}$/.test(id)) return;
    const next = ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id];
    if (next.length > 8) { setNotice("You can save up to 8 neighborhoods. Remove one to add another."); return; }
    setIds(next); setNotice(null);
    try { localStorage.setItem(KEY, JSON.stringify(next)); window.dispatchEvent(new Event(EVENT)); }
    catch { setNotice("Saved for this visit. Enable site storage to keep these places for next time."); }
  }, [ids]);
  return { ids, toggle, notice };
}
