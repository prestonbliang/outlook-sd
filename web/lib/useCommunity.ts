"use client";
import { useCallback, useEffect, useState } from "react";
import { REPORTS_CHANGED, reportSummary, reportsEnabled, type Summary } from "./reports";

type Snapshot = { data: Summary[] | null; error: string | null };
type Entry = { snapshot: Snapshot; subscribers: Set<(value: Snapshot) => void>; pending?: Promise<void>; timer?: ReturnType<typeof setInterval> };
const entries = new Map<number, Entry>();
function entryFor(hours: number): Entry {
  let entry = entries.get(hours);
  if (!entry) { entry = { snapshot: { data: null, error: null }, subscribers: new Set() }; entries.set(hours, entry); }
  return entry;
}
function load(hours: number): Promise<void> {
  const entry = entryFor(hours);
  if (entry.pending) return entry.pending;
  entry.pending = reportSummary(hours).then(data => { entry.snapshot = { data, error: null }; })
    .catch(error => { entry.snapshot = { data: null, error: error instanceof Error ? error.message : "Observations could not load." }; })
    .finally(() => { entry.pending = undefined; entry.subscribers.forEach(notify => notify(entry.snapshot)); });
  return entry.pending;
}
export function useCommunity(hours = 24) {
  const [selection, setSelection] = useState<{ hours: number; snapshot: Snapshot }>({ hours, snapshot: { data: null, error: null } });
  const refresh = useCallback(() => { if (reportsEnabled) void load(hours); }, [hours]);
  useEffect(() => {
    if (!reportsEnabled) return;
    const entry = entryFor(hours);
    const notify = (snapshot: Snapshot) => setSelection({ hours, snapshot });
    notify(entry.snapshot); entry.subscribers.add(notify);
    if (entry.subscribers.size === 1) {
      const refreshWhenVisible = () => { if (!document.hidden) void load(hours); };
      entry.timer = setInterval(refreshWhenVisible, 60000);
    }
    void load(hours);
    const changed = () => { // Submission may finish during an older in-flight read.
      const pending = entry.pending;
      if (pending) void pending.then(() => { if (entry.subscribers.size) return load(hours); }); else void load(hours);
    };
    const visibleRefresh = () => { if (!document.hidden) refresh(); };
    window.addEventListener(REPORTS_CHANGED, changed);
    window.addEventListener("focus", visibleRefresh);
    document.addEventListener("visibilitychange", visibleRefresh);
    return () => {
      entry.subscribers.delete(notify);
      window.removeEventListener(REPORTS_CHANGED, changed); window.removeEventListener("focus", visibleRefresh); document.removeEventListener("visibilitychange", visibleRefresh);
      if (!entry.subscribers.size) { clearInterval(entry.timer); entries.delete(hours); }
    };
  }, [hours, refresh]);
  return { ...(selection.hours === hours ? selection.snapshot : { data: null, error: null }), refresh, enabled: reportsEnabled };
}
