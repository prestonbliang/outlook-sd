"use client";
import type { Tile } from "@/lib/api";
import { forecastState, freshnessLabel } from "@/lib/forecast";
import { useNow } from "@/lib/useNow";

export default function ForecastStatus({ tile, date }: { tile: Tile; date?: string }) {
  const now = useNow();
  const state = forecastState(tile, now, date);
  if (state === "not_applicable") return <span className="data-state muted">Outside coastal forecast coverage</span>;
  if (state === "unavailable") return <span className="data-state state-unavailable">{date ? "No forecast for this day" : "No forecast for today"}</span>;
  return <span className={`data-state state-${state}`}>
    <span aria-hidden="true" className="status-dot" />{state === "stale" ? "Use with caution · data needs updating" : freshnessLabel(tile.run_ts, now)}
  </span>;
}
