"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { usePlace } from "@/lib/usePlace";
import PageIntro from "@/components/PageIntro";
import Icon from "@/components/Icon";
import { comparisonWidth, parseScenarios, scenarioStep, type Scenarios } from "@/lib/scenarios";

/** Two bars: what happens now vs. under the scenario. Widths are shares of the larger value. */
function Compare({ now, then, unit, max, labels }: { now: number; then: number; unit: string; max: number; labels: [string, string] }) {
  const bar = (v: number, cls: string, label: string) => <div className="compare-row">
    <span className="compare-label">{label}</span>
    <span className="compare-track"><span className={`compare-bar ${cls}`} style={{ width: `${comparisonWidth(v, now, then, max)}%` }} /></span>
    <strong className="compare-value">{Math.round(v)} {unit}</strong></div>;
  return <div className="compare" aria-live="polite">{bar(now, "now", labels[0])}{bar(then, "then", labels[1])}</div>;
}

export default function WhatIf() {
  const { placeId } = usePlace();
  const [s, setS] = useState<Scenarios | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cap, setCap] = useState(25);
  const [rise, setRise] = useState(1);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setS(null); setErr(null);
    get<unknown>("scenarios.json", controller.signal).then(parseScenarios).then(setS).catch(e => { if (!controller.signal.aborted) setErr(e.message); });
    return () => controller.abort();
  }, [attempt]);
  const flow = s?.flow, sea = s?.sea_level;
  const capped = flow?.caps.find(c => c.cap_mgd === cap) ?? flow?.caps[0];
  const raised = sea?.rises.find(r => r.rise_ft === rise) ?? sea?.rises[0];
  const today = sea?.rises.find(r => r.rise_ft === 0);
  return <main className="wrap what-if">
    <p className="small"><Link href={`/?place=${placeId ?? ""}`}>← Today</Link></p>
    <PageIntro eyebrow="The scenario lab" title="What if?" description="Big questions, explored through real records. Change river flow or sea level and see how the historical picture changes." icon="water" />
    <p className="notice small">Historical comparisons and model estimates—not live forecasts or official projections.</p>
    {err && <div className="error-panel" role="alert"><p>{err}</p>
      <button className="secondary-button" onClick={() => setAttempt(x => x + 1)}>Try loading scenarios again</button></div>}
    {!s && !err && <p role="status">Loading scenarios…</p>}
    {s && !flow && <section className="scenario"><h2>River-flow scenario unavailable</h2>
      <p>The model evaluation needed for this comparison is missing or incomplete. No estimate is shown.</p>
      <Link href={`/data/?place=${placeId ?? ""}`}>View the data sources</Link></section>}
    {s && !sea && <section className="scenario"><h2>Sea-level scenario unavailable</h2>
      <p>The historical gauge comparison is missing or incomplete. No estimate is shown.</p>
      <a href="https://tidesandcurrents.noaa.gov/stationhome.html?id=9410170">View NOAA’s San Diego gauge</a></section>}

    {flow && capped && <section className="scenario">
      <div className="scenario-number"><Icon name="water" size={24} />01 / River flow</div>
      <h2>Less sewage in the Tijuana River</h2>
      <p>Untreated sewage flows across the border in the Tijuana River and reaches South Bay beaches. Compare the model’s estimates under different river-flow limits.</p>
      {Number.isFinite(flow.recent_mgd) && <p className="small muted">The latest recorded week in this snapshot averaged {flow.recent_mgd} million gallons a day.
        {flow.recent_through && Number.isFinite(Date.parse(flow.recent_through)) && ` Records through ${new Date(flow.recent_through).toLocaleDateString("en-US", { timeZone: "America/Los_Angeles" })}.`}</p>}
      <label className="field-label" htmlFor="cap">If the river never carried more than <strong>{capped.cap_mgd} million gallons a day</strong></label>
      <input id="cap" type="range" min={flow.caps[0].cap_mgd} max={flow.caps.at(-1)!.cap_mgd}
        step={scenarioStep(flow.caps.map(c => c.cap_mgd))} value={capped.cap_mgd} disabled={flow.caps.length < 2}
        onChange={e => { const v = Number(e.target.value); setCap(flow.caps.reduce((a, b) => Math.abs(a.cap_mgd - v) <= Math.abs(b.cap_mgd - v) ? a : b).cap_mgd); }} />
      <p className="small" style={{ fontWeight: 600, margin: "12px 0 4px" }}>Beach water tests our model would flag as unsafe, out of 100 South Bay tests</p>
      <Compare now={flow.no_cap_unsafe_share * 100} then={capped.unsafe_share * 100} unit="of 100" max={flow.no_cap_unsafe_share * 100} labels={["No limit", `Limit ${capped.cap_mgd}`]} />
      <p className="small muted">Our Water model rerun on {flow.samples.toLocaleString()} South Bay beach tests ({flow.period}, the years with river-flow
        records), with river flow capped at the level you chose. It is the model&apos;s estimate, not a measured result.</p>
    </section>}

    {sea && raised && today && <section className="scenario">
      <div className="scenario-number"><Icon name="flood" size={24} />02 / Sea level</div>
      <h2>Higher seas at San Diego Bay</h2>
      <p>When the bay rises above {sea.minor_flood_ft_mllw} ft, low streets near the water start to flood. California&apos;s 2024
        sea-level guidance expects nearly a foot of rise by 2050.</p>
      <label className="field-label" htmlFor="rise">If the sea were <strong>{raised.rise_ft.toFixed(2).replace(/\.?0+$/, "")} ft higher</strong></label>
      <input id="rise" type="range" min={sea.rises[0].rise_ft} max={sea.rises.at(-1)!.rise_ft}
        step={scenarioStep(sea.rises.map(r => r.rise_ft))} value={raised.rise_ft} disabled={sea.rises.length < 2}
        onChange={e => { const v = Number(e.target.value); setRise(sea.rises.reduce((a, b) => Math.abs(a.rise_ft - v) <= Math.abs(b.rise_ft - v) ? a : b).rise_ft); }} />
      <p className="small" style={{ fontWeight: 600, margin: "12px 0 4px" }}>Days per year the bay reaches flood level</p>
      <Compare now={today.days_per_year} then={raised.days_per_year} unit="days" max={Math.max(raised.days_per_year, today.days_per_year, 1)} labels={["Now", `+${raised.rise_ft} ft`]} />
      <p className="small muted">Every hourly water level measured at NOAA&apos;s San Diego Bay gauge, {sea.period}, raised by the amount you chose.
        No model involved: this is the real record of tides and storms, shifted up.</p>
    </section>}

    <p className="disclaimer">Scenarios are estimates from public data, for discussion. They are not official projections.</p>
  </main>;
}
