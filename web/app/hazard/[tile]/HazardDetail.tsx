"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import ForecastChart from "@/components/ForecastChart";
import LevelBadge from "@/components/LevelBadge";
import ReportBox from "@/components/ReportBox";
import SourceLine from "@/components/SourceLine";
import ForecastStatus from "@/components/ForecastStatus";
import { advisoryIsCurrent, currentDay, dateLabel, localDate, observationIsCurrent } from "@/lib/forecast";
import { usePlace } from "@/lib/usePlace";
import { useNow } from "@/lib/useNow";
import { Hazard, TILE_LABEL, tileMeaning, TILE_NAME, TileName, dayName, get } from "@/lib/api";

function windowText(h: Hazard) {
  const today = currentDay(h);
  if (!today) return "No forecast for today";
  let through = today.date;
  for (const day of h.days.filter(d => d.date > today.date)) {
    const next = new Date(`${through}T12:00:00Z`); next.setUTCDate(next.getUTCDate() + 1);
    if (day.verdict !== today.verdict || !Number.isFinite(day.value) || day.date !== next.toISOString().slice(0, 10)) break;
    through = day.date;
  }
  return through === today.date ? `${today.verdict} · Today` : `${today.verdict} through ${dateLabel(through)}`;
}

// Fire levels are ranks: cut-offs at the 75th, 90th and 98th percentiles of all 2023 area-days
const FIRE_RANK: Record<string, string> = { low: "A typical day", moderate: "Among the riskiest 25% of days",
  high: "Among the riskiest 10% of days", very_high: "Among the riskiest 2% of days" };

function valueText(tile: TileName, d: Hazard["days"][number]) {
  if (d.value === null || d.value === undefined) return "";
  if (tile === "water") return `${Math.round(d.value * 100)}% chance above the state standard`;
  if (tile === "flood") return `Peak ${d.value.toFixed(1)} ft${typeof d.high_end === "number" ? ` (high end ${d.high_end.toFixed(1)} ft)` : ""}`;
  if (tile === "heat" && typeof d.expected_calls === "number" && typeof d.normal_calls === "number")
    return `${(d.expected_calls as number).toFixed(0)} calls expected vs ${(d.normal_calls as number).toFixed(0)} normal${d.high_f ? `; high ${d.high_f}°F` : ""}`;
  if (tile === "heat") return `CalHeatScore ${d.value} of 4`;
  if (tile === "air") return `AQI ${Math.round(d.value)} (${d.pollutant})${typeof d.high_end === "number" ? `, high-end forecast ${Math.round(d.high_end)}` : ""}`;
  if (tile === "fire") return `${d.level ? FIRE_RANK[d.level] : "No risk rank available"} for a new large fire (10+ acres) nearby` +
    (d.county_expected_fires !== null && d.county_expected_fires !== undefined ? `; county-wide, ${d.county_expected_fires} such fires expected` : "");
  return String(d.value);
}

export default function HazardDetail({ tile }: { tile: TileName }) {
  useNow(); // Re-evaluate current-day labels and observation age while this page stays open.
  const { placeId, error: placeError, retry } = usePlace();
  const [h, setH] = useState<Hazard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!placeId) return;
    const controller = new AbortController();
    setH(null); setErr(null);
    get<Hazard>(`hazard/${tile}/${placeId}.json`, controller.signal).then(setH)
      .catch((e) => { if (!controller.signal.aborted) setErr(e.message); });
    return () => controller.abort();
  }, [tile, placeId, attempt]);

  if (err || placeError) return <main className="wrap"><h1>{TILE_NAME[tile]} forecast</h1><div className="error-panel" role="alert"><p>{err ?? placeError}</p>
    <button className="secondary-button" onClick={() => { retry(); setAttempt(x => x + 1); }}>Try again</button></div><Link href="/">Back to today</Link></main>;
  if (!h) return <main className="wrap" aria-busy="true"><h1>{TILE_NAME[tile]} forecast</h1><p role="status">Loading neighborhood details…</p></main>;
  const d0 = currentDay(h);
  const upcoming = h.days.filter(day => day.date >= localDate());
  const advice = d0 && h.what_to_do_by_date?.[d0.date] ? h.what_to_do_by_date[d0.date] :
    !h.days.length || h.days[0]?.date === d0?.date ? h.what_to_do : "Guidance for the current day is unavailable in this snapshot. Check the official source for current advice.";
  return (
    <main className="wrap">
      <p className="small"><Link href={`/?place=${h.place.id}`}>← {h.place.name}</Link></p>
      <h1>{TILE_LABEL[tile]} · {h.place.name}</h1>
      <p className="small muted" style={{ margin: "6px 0 0" }}>{tileMeaning(h)}</p>
      <ForecastStatus tile={h} />
      <p style={{ fontSize: 20, fontWeight: 600, margin: "8px 0 4px" }}>{windowText(h)}</p>
      {d0 && <p style={{ margin: 0 }}><LevelBadge tile={tile} level={d0.level} /> <span className="muted">· {valueText(tile, d0)}</span></p>}
      {h.unit && <p className="small muted" style={{ margin: "4px 0 0" }}>
        {tile === "water" ? `Nearest monitored beach: ${h.unit.name}` : tile === "flood" ? `${h.unit.name}; levels in ${h.units}` : h.unit.name}
      </p>}
      {h.reason && !d0 && <p>{h.reason}</p>}
      {h.official_advisory.active !== false && h.official_advisory.headline && (
        <p role="note" style={{ borderLeft: "6px solid var(--lvl-high)", paddingLeft: 10 }}>NWS: {h.official_advisory.headline}
          {!advisoryIsCurrent(h.official_advisory) && " · Last recorded warning; check the official source for its current status."}</p>
      )}
      {(tile === "flood" || tile === "fire") && (h.official_advisory.active === null || !advisoryIsCurrent(h.official_advisory)) && <p className="notice small">Official alert status could not be confirmed. <a href={h.official_advisory.url}>Check the official source</a>.</p>}

      {h.factors.length > 0 && <>
        <h2 style={{ marginTop: 20 }}>Why</h2>
        <ul>{h.factors.map((f) => <li key={f.label}>{f.label}{f.value ? `: ${f.value}` : ""}</li>)}</ul>
      </>}

      {tile === "air" && h.current && <p>{observationIsCurrent(h.current.time) ? "Recent observation" : "Last recorded observation"}: AQI {h.current.aqi} ({h.current.parameter}) at {h.current.site} — {h.current.verdict}. <span className="small muted">{new Date(h.current.time).toLocaleString("en-US", { timeZone: "America/Los_Angeles" })} PT.</span></p>}
      {tile === "fire" && <>
        {h.red_flag && h.red_flag.length > 0 && h.red_flag.map((r) => <p key={r}>{r}</p>)}
        {!h.active_fires_available && <p className="notice small">Current incident data could not be confirmed. Any listed records may be outdated. <a href="https://www.fire.ca.gov/incidents">Check CAL FIRE</a>.</p>}
        {h.active_fires && h.active_fires.length > 0
          ? <ul>{h.active_fires.map((f) => <li key={f.name}><a href={f.url}>{f.name}</a>: {f.acres ?? "unknown"} acres, {f.km} km away</li>)}</ul>
          : h.active_fires_available && <p>No active CAL FIRE incidents within 50 km.</p>}
      </>}

      {h.series && <><h2 style={{ marginTop: 20 }}>Past 7 days and forecast</h2><ForecastChart series={h.series} /></>}

      {upcoming.length > 0 && <>
        <h2 style={{ marginTop: 20 }}>Next days</h2>
        <div className="table-scroll"><table>
          <caption className="sr-only">{TILE_NAME[tile]} forecast by day for {h.place.name}</caption>
          <thead><tr><th scope="col">Day</th><th scope="col">Level</th><th scope="col">Detail</th></tr></thead>
          <tbody>{upcoming.map((d) => (
            <tr key={d.date}><td>{dayName(d.date, "long")}</td><td><LevelBadge tile={tile} level={d.level} /></td>
              <td>{valueText(tile, d)}</td></tr>))}</tbody>
        </table></div>
      </>}

      <h2 style={{ marginTop: 20 }}>What to do</h2>
      <p>{advice}</p>
      {h.cool_zones && h.cool_zones.length > 0 && <>
        <h2 style={{ marginTop: 20 }}>Air-conditioned places nearby</h2>
        <p className="small muted">County of San Diego Cool Zones: free, air-conditioned public places (season June 1 – October 31). Check hours before you go.</p>
        <ul className="cool-list">{h.cool_zones.map(z => <li key={z.name}><strong>{z.name}</strong> · {(z.km * 0.621).toFixed(1)} mi
          <br /><span className="small">{z.address}{z.phone ? ` · ${z.phone}` : ""}{z.pets ? ` · Pets: ${z.pets}` : ""}</span>
          {z.hours && <details><summary>Hours</summary><p className="small" style={{ whiteSpace: "pre-line", margin: 0 }}>{z.hours}</p></details>}</li>)}</ul>
        <p className="small"><a href="https://www.sandiegocounty.gov/hhsa/programs/ais/cool_zones.html">All County Cool Zones</a></p>
      </>}

      <p><Link href={`/map/?place=${h.place.id}&hazard=${tile}`}>Explore this hazard on the map →</Link></p>
      {tile === "water" && h.place.coastal === false ? <p className="notice">Choose a coastal neighborhood on the map to report beach conditions.</p> :
        <ReportBox key={`${h.place.id}-${tile}`} tile={tile} placeId={h.place.id} placeName={h.place.name} />}

      {h.metrics && <p className="small">How accurate is this? {h.metrics.headline} <Link href={`/track-record/?place=${h.place.id}`}>Track record</Link></p>}
      <SourceLine sources={h.sources} updated={h.run_ts} stale={h.stale_inputs} />
      <p className="small"><a href={h.official_advisory.url}>Official source for {TILE_NAME[tile].toLowerCase()}</a></p>
      <p className="disclaimer">Forecast from the Outlook SD model, not an official advisory.</p>
    </main>
  );
}
