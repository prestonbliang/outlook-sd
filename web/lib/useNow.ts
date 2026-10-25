"use client";
import { useSyncExternalStore } from "react";

// One clock for all freshness displays, suspended while hidden and removed after the last subscriber.
let now = Date.now();
let stop: (() => void) | undefined;
const subscribers = new Set<() => void>();
function subscribe(notify: () => void) {
  subscribers.add(notify);
  if (!stop) {
    const update = () => {
      if (document.hidden) return;
      now = Date.now();
      subscribers.forEach(listener => listener());
    };
    update();
    const timer = setInterval(update, 60000);
    document.addEventListener("visibilitychange", update);
    window.addEventListener("focus", update);
    stop = () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", update);
      window.removeEventListener("focus", update);
      stop = undefined;
    };
  }
  return () => { subscribers.delete(notify); if (!subscribers.size) stop?.(); };
}
export const useNow = () => useSyncExternalStore(subscribe, () => now, () => 0);
