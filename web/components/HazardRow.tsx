"use client";
import Link from "next/link";
import { useState } from "react";
import { TILE_NAME, Tile, levelColor } from "@/lib/api";
import DayStrip from "./DayStrip";
import SourceLine from "./SourceLine";

/** One hazard: 6 px level bar, name, verdict, reason (above Low), 3-day strip. Tap expands the why. */
export default function HazardRow({ tile, placeId, onSelect }: { tile: Tile; placeId: string; onSelect?: () => void }) {
  const [open, setOpen] = useState(false);
  const today = tile.days[0];
  const level = today?.level ?? null;
  const verdict = today?.verdict ?? tile.verdict ?? "";
  const showReason = tile.reason && (level === null || !["low", "good"].includes(level));
  const id = `row-${tile.tile}`;
  return (
    <section style={{ display: "flex", borderBottom: "1px solid var(--rule)" }} aria-labelledby={id}>
      <div aria-hidden style={{ width: 6, background: levelColor(tile.tile, level), flex: "none" }} />
      <div style={{ flex: 1, padding: "12px 0 12px 12px", minWidth: 0 }}>
        <button onClick={() => { setOpen(!open); onSelect?.(); }} aria-expanded={open} aria-controls={`${id}-more`}
                style={{ all: "unset", cursor: "pointer", display: "flex", gap: 12, width: "100%", alignItems: "flex-start" }}>
          <span style={{ flex: 1, minWidth: 0 }}>
            <span id={id} style={{ display: "block", fontWeight: 600 }}>{TILE_NAME[tile.tile]}</span>
            <span style={{ display: "block", fontWeight: 600, fontSize: 20 }}>{verdict}
              {tile.tile === "air" && tile.current && <span className="muted" style={{ fontWeight: 400, fontSize: 16 }}> · AQI {tile.current.aqi} now</span>}
            </span>
            {showReason && <span className="small muted" style={{ display: "block" }}>{tile.reason}</span>}
          </span>
          <DayStrip tile={tile.tile} days={tile.days} />
        </button>
        {open && (
          <div id={`${id}-more`} style={{ paddingTop: 8 }}>
            {tile.factors.length > 0 && (
              <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                {tile.factors.map((f) => <li key={f.label}>{f.label}{f.value ? `: ${f.value}` : ""}</li>)}
              </ul>
            )}
            <p className="small" style={{ margin: "6px 0 0" }}>
              <Link href={`/hazard/${tile.tile}/?place=${placeId}`}>{TILE_NAME[tile.tile]} details</Link>
              {" · "}<a href={tile.official_advisory.url}>Official source</a>
            </p>
            <SourceLine sources={tile.sources} updated={tile.run_ts} stale={tile.stale_inputs} />
          </div>
        )}
      </div>
    </section>
  );
}
