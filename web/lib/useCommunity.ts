"use client";
import { useCallback, useEffect, useState } from "react";
import { REPORTS_CHANGED, reportSummary, reportsEnabled, type Summary } from "./reports";

export function useCommunity(hours = 24) {
  const [data, setData] = useState<Summary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);
  useEffect(() => {
    if (!reportsEnabled) return;
    let controller: AbortController | undefined;
    let active = true;
    setData(null); setError(null);
    async function load() {
      controller?.abort();
      const request = new AbortController();
      controller = request;
      try {
        const rows = await reportSummary(hours, request.signal);
        if (active && !request.signal.aborted) { setData(rows); setError(null); }
      } catch (e) {
        if (active && !request.signal.aborted) { setError((e as Error).message); setData(null); }
      }
    }
    void load();
    const interval = setInterval(() => { if (!document.hidden) void load(); }, 60000);
    window.addEventListener(REPORTS_CHANGED, load);
    window.addEventListener("focus", load);
    return () => {
      active = false; controller?.abort(); clearInterval(interval);
      window.removeEventListener(REPORTS_CHANGED, load); window.removeEventListener("focus", load);
    };
  }, [hours, version]);
  return { data, error, refresh, enabled: reportsEnabled };
}
