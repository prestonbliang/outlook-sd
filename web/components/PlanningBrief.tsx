"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { LEVEL_WORD, TILE_LABEL, TILE_ORDER, type Outlook, type TileName } from "@/lib/api";
import { advisoryIsCurrent, dateLabel, parseHazardFocus, planningDays } from "@/lib/forecast";
import { useNow } from "@/lib/useNow";

const KEY = "outlook-sd-planning-focus";
const PRESETS: { name: string; tiles: TileName[] }[] = [
  { name: "All hazards", tiles: TILE_ORDER }, { name: "Beach visit", tiles: ["water", "heat", "flood"] },
  { name: "Outdoor time", tiles: ["air", "heat", "fire"] },
];
export default function PlanningBrief({ outlook }: { outlook: Outlook }) {
  const now = useNow();
  const [focus, setFocus] = useState<TileName[]>(TILE_ORDER);
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    const sync = () => { try { setFocus(parseHazardFocus(localStorage.getItem(KEY), TILE_ORDER)); } catch { /* In-memory preferences still work. */ } };
    sync(); window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);
  function select(tiles: TileName[]) {
    const next = TILE_ORDER.filter(t => tiles.includes(t));
    setFocus(next); setNotice(null);
    try { localStorage.setItem(KEY, JSON.stringify(next)); }
    catch { setNotice("Focus saved for this visit. Enable site storage to keep it next time."); }
  }
  const days = planningDays(outlook.tiles, focus, now || Date.now());
  const warnings = outlook.tiles.filter(t => t.official_advisory.active !== false && t.official_advisory.headline);
  return <section className="planning-brief" aria-labelledby="planning-heading">
    <div className="brief-heading"><div><p className="eyebrow">Your planning brief</p><h2 id="planning-heading">Plan the next three days</h2></div></div>
    <p className="small muted">Choose what matters for your plans. Preferences stay on this device.</p>
    {warnings.length > 0 && <p className="notice small" role="note">Official warnings recorded: {warnings.map((t, i) => <span key={t.tile}>
      {i > 0 && "; "}<a href={t.official_advisory.url}>{t.official_advisory.headline}</a>
      {!advisoryIsCurrent(t.official_advisory, now) && " (status needs checking)"}</span>)}. Follow official guidance.</p>}
    <div className="planning-layout"><div className="planning-controls"><div className="planning-presets" aria-label="Planning presets">{PRESETS.map(p => <button key={p.name} className="place-chip"
      aria-pressed={p.tiles.length === focus.length && p.tiles.every(t => focus.includes(t))} onClick={() => select(p.tiles)}>{p.name}</button>)}</div>
    <details className="planning-focus"><summary>Choose hazards ({focus.length})</summary><fieldset>
      <legend className="sr-only">Hazards in your planning brief</legend>
      {TILE_ORDER.map(t => <label key={t}><input type="checkbox" checked={focus.includes(t)}
        onChange={() => select(focus.includes(t) ? focus.filter(x => x !== t) : [...focus, t])} />{TILE_LABEL[t]}</label>)}
    </fieldset></details>
    {notice && <p role="status" className="small">{notice}</p>}
    </div>
    {!focus.length ? <p className="small" role="status">Select at least one hazard to see your planning brief.</p> :
      <div className="planning-days">{days.map(d => <article key={d.date} className={`planning-day ${d.attention.length ? "planning-attention" : ""}`}>
        <h3>{dateLabel(d.date, new Date(now || Date.now()))}</h3>
        <p className="planning-summary">{d.attention.length ? `${d.attention.length} ${d.attention.length === 1 ? "hazard needs" : "hazards need"} attention` :
          d.incomplete ? "Updates needed" : d.current ? "No elevated ratings" : "Outside coverage"}</p>
        <p className="small muted">{d.current} of {focus.length} ratings current{d.incomplete ? "; others need checking" : ""}.</p>
        <details><summary>View forecasts</summary><ul>{d.items.map(item => <li key={item.hazard}>
          <Link href={`/map/?place=${outlook.place.id}&hazard=${item.hazard}&date=${d.date}`}>{TILE_LABEL[item.hazard]}</Link>
          <span className={`plan-state state-${item.state}`}>{item.state === "current" ? LEVEL_WORD[item.day?.level ?? ""] ?? "Not rated" :
            item.state === "stale" ? "Needs updating" : item.state === "not_applicable" ? "Outside coverage" : "No forecast"}</span>
        </li>)}</ul></details>
      </article>)}</div>}</div>
    <p className="small muted planning-method">Attention means Moderate or higher; for air, Unhealthy for sensitive groups or higher.
      Only current forecasts contribute. Missing data is unknown. This is not a combined risk score or an official advisory.</p>
  </section>;
}
