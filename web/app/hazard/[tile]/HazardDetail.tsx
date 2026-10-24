"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import ForecastChart from "@/components/ForecastChart";
import LevelBadge from "@/components/LevelBadge";
import ReportBox from "@/components/ReportBox";
import SourceLine from "@/components/SourceLine";
import { Hazard, TILE_NAME, TileName, dayName, get } from "@/lib/api";

function windowText(h: Hazard) {
  const w = h.window;
  if (!w) return h.verdict ?? "";
  const today = h.days[0]?.date;
  return w.through === today ? `${w.verdict} today` : `${w.verdict} through ${dayName(w.through, "long")}`;
}

// Fire levels are ranks: cut-offs at the 75th, 90th and 98th percentiles of all 2023 area-days
const FIRE_RANK: Record<string, string> = { low: "A typical day", moderate: "Among the riskiest 25% of days",
  high: "Among the riskiest 10% of days", very_high: "Among the riskiest 2% of days" };

function valueText(tile: TileName, d: Hazard["days"][number]) {
  if (d.value === null || d.value === undefined) return "";
  if (tile === "water") return `${Math.round(d.value * 100)}% chance above the state standard`;
  if (tile === "flood") return `Peak ${d.value.toFixed(1)} ft${d.high_end ? ` (high end ${(d.high_end as number).toFixed(1)} ft)` : ""}`;
  if (tile === "heat" && d.expected_calls !== undefined)
    return `${(d.expected_calls as number).toFixed(0)} calls expected vs ${(d.normal_calls as number).toFixed(0)} normal${d.high_f ? `; high ${d.high_f}°F` : ""}`;
  if (tile === "heat") return `CalHeatScore ${d.value} of 4`;
  if (tile === "air") return `AQI ${Math.round(d.value)} (${d.pollutant})${d.high_end ? `, could reach ${Math.round(d.high_end as number)}` : ""}`;
  if (tile === "fire") return `${FIRE_RANK[d.level ?? "low"]} for a new large fire (10+ acres) nearby` +
    (d.county_expected_fires !== null && d.county_expected_fires !== undefined ? `; county-wide, ${d.county_expected_fires} such fires expected` : "");
  return String(d.value);
}

export default function HazardDetail({ tile }: { tile: TileName }) {
  const [h, setH] = useState<Hazard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const place = new URLSearchParams(window.location.search).get("place") || "downtown";
    get<Hazard>(`hazard/${tile}/${place}.json`).then(setH).catch((e) => setErr(e.message));
  }, [tile]);

  if (err) return <main className="wrap"><p role="alert">Could not load this forecast: {err}</p><Link href="/">Back</Link></main>;
  if (!h) return <main className="wrap"><p>Loading…</p></main>;
  const d0 = h.days[0];
  return (
    <main className="wrap">
      <p className="small"><Link href={`/?place=${h.place.id}`}>← {h.place.name}</Link></p>
      <h1>{TILE_NAME[tile]} · {h.place.name}</h1>
      <p style={{ fontSize: 20, fontWeight: 600, margin: "8px 0 4px" }}>{windowText(h)}</p>
      {d0 && <p style={{ margin: 0 }}><LevelBadge tile={tile} level={d0.level} /> <span className="muted">· {valueText(tile, d0)}</span></p>}
      {h.unit && <p className="small muted" style={{ margin: "4px 0 0" }}>
        {tile === "water" ? `Nearest monitored beach: ${h.unit.name}` : tile === "flood" ? `${h.unit.name}; levels in ${h.units}` : h.unit.name}
      </p>}
      {h.reason && !d0 && <p>{h.reason}</p>}
      {h.official_advisory.active && h.official_advisory.headline && (
        <p role="note" style={{ borderLeft: "6px solid var(--lvl-high)", paddingLeft: 10 }}>NWS: {h.official_advisory.headline}</p>
      )}

      {h.factors.length > 0 && <>
        <h2 style={{ marginTop: 20 }}>Why</h2>
        <ul>{h.factors.map((f) => <li key={f.label}>{f.label}{f.value ? `: ${f.value}` : ""}</li>)}</ul>
      </>}

      {tile === "air" && h.current && <p>Now: AQI {h.current.aqi} ({h.current.parameter}) at {h.current.site} — {h.current.verdict}.</p>}
      {tile === "fire" && <>
        {h.red_flag && h.red_flag.length > 0 && h.red_flag.map((r) => <p key={r}>{r}</p>)}
        {h.active_fires && h.active_fires.length > 0
          ? <ul>{h.active_fires.map((f) => <li key={f.name}><a href={f.url}>{f.name}</a>: {f.acres} acres, {f.km} km away</li>)}</ul>
          : <p>No active CAL FIRE incidents within 50 km.</p>}
      </>}

      {h.series && <><h2 style={{ marginTop: 20 }}>Past 7 days and forecast</h2><ForecastChart series={h.series} /></>}

      {h.days.length > 0 && <>
        <h2 style={{ marginTop: 20 }}>Next days</h2>
        <table>
          <thead><tr><th>Day</th><th>Level</th><th>Detail</th></tr></thead>
          <tbody>{h.days.map((d) => (
            <tr key={d.date}><td>{dayName(d.date, "long")}</td><td><LevelBadge tile={tile} level={d.level} /></td>
              <td>{valueText(tile, d)}</td></tr>))}</tbody>
        </table>
      </>}

      <h2 style={{ marginTop: 20 }}>What to do</h2>
      <p>{h.what_to_do}</p>

      <ReportBox tile={tile} placeId={h.place.id} placeName={h.place.name} />

      {h.metrics && <p className="small">How accurate is this? {h.metrics.headline} <Link href={`/track-record/?place=${h.place.id}`}>Track record</Link></p>}
      <SourceLine sources={h.sources} updated={h.run_ts} stale={h.stale_inputs} />
      <p className="small"><a href={h.official_advisory.url}>Official source for {TILE_NAME[tile].toLowerCase()}</a></p>
      <p className="disclaimer">Forecast from the Outlook SD model, not an official advisory.</p>
    </main>
  );
}
