"use client";
import Link from "next/link";
import { useState } from "react";
import { CoolZone, TILE_LABEL, tileMeaning, Tile, levelColor } from "@/lib/api";
import DayStrip from "./DayStrip";
import SourceLine from "./SourceLine";
import ForecastStatus from "./ForecastStatus";
import { currentDay, dateLabel, observationIsCurrent } from "@/lib/forecast";

/** One hazard: 6 px level bar, name, verdict, reason (above Low), 3-day strip. Tap expands the why. */
export default function HazardRow({ tile, placeId, onSelect, coolZone }: { tile: Tile; placeId: string; onSelect?: () => void; coolZone?: CoolZone }) {
  const [open, setOpen] = useState(false);
  const today = currentDay(tile);
  const level = today?.level ?? null;
  const verdict = today?.verdict ?? tile.verdict ?? "No forecast for today";
  const showReason = tile.reason && (level === null || !["low", "good"].includes(level));
  const id = `row-${tile.tile}`;
  const coolOff = coolZone && level && level !== "low" && level !== "good";
  return (
    <section className="hazard-card" style={{ display: "flex", borderBottom: "1px solid var(--rule)" }} aria-labelledby={id}>
      <div aria-hidden style={{ width: 6, background: levelColor(tile.tile, level), flex: "none" }} />
      <div className="hazard-card-body" style={{ flex: 1, minWidth: 0 }}>
        <button className="hazard-toggle" onClick={() => { setOpen(!open); onSelect?.(); }} aria-expanded={open} aria-controls={`${id}-more`}>
          <span style={{ flex: 1, minWidth: 0 }}>
            <span style={{ display: "block", fontWeight: 600 }}><span id={id}>{TILE_LABEL[tile.tile]}</span>
              {tile.tile === "water" && tile.unit && <span className="muted" style={{ fontWeight: 400 }}> · {tile.unit.name}</span>}</span>
            <span style={{ display: "block", fontWeight: 600, fontSize: 20 }}>{verdict}
              {tile.tile === "air" && tile.current && <span className="muted" style={{ fontWeight: 400, fontSize: 16 }}> · AQI {tile.current.aqi} {observationIsCurrent(tile.current.time) ? "recently observed" : "last observed"}</span>}
            </span>
            {showReason && <span className="small muted" style={{ display: "block" }}>{tile.reason}</span>}
          </span>
          <DayStrip tile={tile.tile} days={tile.days} />
        </button>
        {coolOff && <p className="small cool-line">Cool off nearby: {coolZone.name}, {(coolZone.km * 0.621).toFixed(1)} mi</p>}
        <ForecastStatus tile={tile} />
        {tile.official_advisory.active && tile.official_advisory.headline && <p className="notice small"><a href={tile.official_advisory.url}>{tile.official_advisory.headline}</a></p>}
        {!today && tile.days[0] && <p className="small muted">Next available forecast: {dateLabel(tile.days[0].date)}</p>}
        {open && (
          <div id={`${id}-more`} style={{ paddingTop: 8 }}>
            <p className="small" style={{ margin: "0 0 6px" }}>{tileMeaning(tile)}</p>
            {tile.factors.length > 0 && <>
              <p className="small" style={{ margin: "8px 0 2px", fontWeight: 600 }}>Main reasons</p>
              <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                {tile.factors.map((f) => <li key={f.label}>{f.label}{f.value ? `: ${f.value}` : ""}</li>)}
              </ul>
            </>}
            <p className="small" style={{ margin: "6px 0 0" }}>
              <Link href={`/hazard/${tile.tile}/?place=${placeId}`}>Full {TILE_LABEL[tile.tile].toLowerCase()} forecast</Link>
              {" · "}<Link href={`/map/?place=${placeId}&hazard=${tile.tile}#map-report`}>Map & reports</Link>
              {" · "}<a href={tile.official_advisory.url}>Official source</a>
            </p>
            <SourceLine sources={tile.sources} updated={tile.run_ts} stale={tile.stale_inputs} />
          </div>
        )}
      </div>
    </section>
  );
}
