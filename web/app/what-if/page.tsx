"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { usePlace } from "@/lib/usePlace";

type Scenarios = {
  flow: { period: string; samples: number; no_cap_unsafe_share: number; caps: { cap_mgd: number; unsafe_share: number }[];
    recent_mgd?: number } | null;
  sea_level: { period: string; minor_flood_ft_mllw: number; rises: { rise_ft: number; days_per_year: number }[] } | null;
};

/** Two bars: what happens now vs. under the scenario. Widths are shares of the larger value. */
function Compare({ now, then, unit, max, labels }: { now: number; then: number; unit: string; max: number; labels: [string, string] }) {
  const bar = (v: number, cls: string, label: string) => <div className="compare-row">
    <span className="compare-label">{label}</span>
    <span className="compare-track"><span className={`compare-bar ${cls}`} style={{ width: `${Math.max(1, (v / max) * 100)}%` }} /></span>
    <strong className="compare-value">{Math.round(v)} {unit}</strong></div>;
  return <div className="compare" aria-live="polite">{bar(now, "now", labels[0])}{bar(then, "then", labels[1])}</div>;
}

export default function WhatIf() {
  const { placeId } = usePlace();
  const [s, setS] = useState<Scenarios | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cap, setCap] = useState(25);
  const [rise, setRise] = useState(1);
  useEffect(() => {
    const controller = new AbortController();
    get<Scenarios>("scenarios.json", controller.signal).then(setS).catch(e => { if (!controller.signal.aborted) setErr(e.message); });
    return () => controller.abort();
  }, []);
  const flow = s?.flow, sea = s?.sea_level;
  const capped = flow?.caps.find(c => c.cap_mgd === cap);
  const raised = sea?.rises.find(r => r.rise_ft === rise);
  const today = sea?.rises.find(r => r.rise_ft === 0);
  return <main className="wrap what-if">
    <p className="small"><Link href={`/?place=${placeId ?? ""}`}>← Today</Link></p>
    <h1>What if?</h1>
    <p>San Diego is making big decisions about sewage and rising seas. Move the sliders to see what our data says would change.</p>
    {err && <div className="error-panel" role="alert"><p>{err}</p></div>}
    {!s && !err && <p role="status">Loading scenarios…</p>}

    {flow && capped && <section className="scenario">
      <h2>Less sewage in the Tijuana River</h2>
      <p>Untreated sewage flows across the border in the Tijuana River and reaches South Bay beaches. The South Bay treatment
        plant is being expanded from 25 to 50 million gallons a day.{flow.recent_mgd !== undefined &&
        ` Over the past week the river carried about ${flow.recent_mgd} million gallons a day across the border.`}</p>
      <label className="field-label" htmlFor="cap">If the river never carried more than <strong>{cap} million gallons a day</strong></label>
      <input id="cap" type="range" min={0} max={100} step={5} value={cap} onChange={e => setCap(Number(e.target.value))} />
      <p className="small" style={{ fontWeight: 600, margin: "12px 0 4px" }}>Beach water tests our model would flag as unsafe, out of 100 South Bay tests</p>
      <Compare now={flow.no_cap_unsafe_share * 100} then={capped.unsafe_share * 100} unit="of 100" max={flow.no_cap_unsafe_share * 100} labels={["No limit", `Limit ${cap}`]} />
      <p className="small muted">Our Water model rerun on {flow.samples.toLocaleString()} South Bay beach tests ({flow.period}, the years with river-flow
        records), with river flow capped at the level you chose. It is the model&apos;s estimate, not a measured result.</p>
    </section>}

    {sea && raised && today && <section className="scenario">
      <h2>Higher seas at San Diego Bay</h2>
      <p>When the bay rises above {sea.minor_flood_ft_mllw} ft, low streets near the water start to flood. California&apos;s 2024
        sea-level guidance expects nearly a foot of rise by 2050.</p>
      <label className="field-label" htmlFor="rise">If the sea were <strong>{rise.toFixed(2).replace(/\.?0+$/, "")} ft higher</strong></label>
      <input id="rise" type="range" min={0} max={3} step={0.25} value={rise} onChange={e => setRise(Number(e.target.value))} />
      <p className="small" style={{ fontWeight: 600, margin: "12px 0 4px" }}>Days per year the bay reaches flood level</p>
      <Compare now={today.days_per_year} then={raised.days_per_year} unit="days" max={Math.max(raised.days_per_year, today.days_per_year, 1)} labels={["Now", `+${rise} ft`]} />
      <p className="small muted">Every hourly water level measured at NOAA&apos;s San Diego Bay gauge, {sea.period}, raised by the amount you chose.
        No model involved: this is the real record of tides and storms, shifted up.</p>
    </section>}

    <p className="disclaimer">Scenarios are estimates from public data, for discussion. They are not official projections.</p>
  </main>;
}
