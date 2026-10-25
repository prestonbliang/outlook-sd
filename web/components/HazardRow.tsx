"use client";
import Link from "next/link";
import { useState } from "react";
import type { CSSProperties } from "react";
import Icon from "./Icon";
import { CoolZone, ELEVATED, TILE_LABEL, tileMeaning, Tile, levelColor } from "@/lib/api";
import DayStrip from "./DayStrip";
import SourceLine from "./SourceLine";
import ForecastStatus from "./ForecastStatus";
import { advisoryIsCurrent, currentDay, dateLabel, observationIsCurrent } from "@/lib/forecast";

/** One hazard: 6 px level bar, name, verdict, reason (above Low), 3-day strip. Tap expands the why. */
export default function HazardRow({ tile, placeId, onSelect, coolZone }: { tile: Tile; placeId: string; onSelect?: () => void; coolZone?: CoolZone }) {
  const [open, setOpen] = useState(false);
  const today = currentDay(tile);
  const level = today?.level ?? null;
  const verdict = today?.verdict ?? tile.verdict ?? "No forecast for today";
  const showReason = tile.reason && (level === null || !["low", "good"].includes(level));
  const id = `row-${tile.tile}`;
  // Heat: Moderate or worse. Air: only when it is unhealthy for sensitive groups or worse.
  const coolOff = coolZone && level && (tile.tile === "air" ? ELEVATED.has(level) : level !== "low");
  return (
    <section className={`hazard-card hazard-${tile.tile}`} style={{ "--risk-color": levelColor(tile.tile, level) } as CSSProperties} aria-labelledby={id}>
      <div className="hazard-card-body">
        <button className="hazard-toggle" onClick={() => { setOpen(!open); onSelect?.(); }} aria-expanded={open} aria-controls={`${id}-more`}>
          <span className="hazard-card-heading"><span className="hazard-identity"><span className="hazard-icon"><Icon name={tile.tile} size={23} /></span><span id={id}>{TILE_LABEL[tile.tile]}</span></span><span className="expand-icon"><Icon name="chevron" size={18} /></span></span>
          <span className="hazard-verdict">{verdict}</span>
          {tile.tile === "water" && tile.unit && <span className="small muted hazard-unit">{tile.unit.name}</span>}
          {tile.tile === "air" && tile.current && <span className="small muted">AQI {tile.current.aqi} · {observationIsCurrent(tile.current.time) ? "recently observed" : "last observed"}</span>}
          {showReason && <span className="small muted hazard-reason">{tile.reason}</span>}
        </button>
        {coolOff && <p className="small cool-line">{tile.tile === "air" ? "Clean indoor air nearby" : "Cool off nearby"}: {coolZone.name}, {(coolZone.km * 0.621).toFixed(1)} mi</p>}
        <div className="hazard-card-meta"><ForecastStatus tile={tile} /><DayStrip tile={tile.tile} days={tile.days} /></div>
        {tile.official_advisory.active !== false && tile.official_advisory.headline && <p className="notice small"><a href={tile.official_advisory.url}>{tile.official_advisory.headline}</a>
          {!advisoryIsCurrent(tile.official_advisory) && " · Last recorded warning; check the official source for its current status."}</p>}
        {!today && tile.days[0] && <p className="small muted">Next available forecast: {dateLabel(tile.days[0].date)}</p>}
        {open && (
          <div id={`${id}-more`} className="hazard-expanded">
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
