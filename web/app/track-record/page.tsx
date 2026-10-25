"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { TILE_LABEL, TILE_ORDER, TileName, TrackSummary, get } from "@/lib/api";
import { usePlace } from "@/lib/usePlace";

type Community = { problem_reports: number; all_clear_reports: number; problem_on_elevated_days: number; problem_rated: number;
  all_clear_on_low_days: number; all_clear_rated: number; since: string };
type Live = { scored: number; hits: number; since: string; observed_fires?: number; expected_fires?: number };
type Odor = { test_days: number; event_days: number; auc: Record<string, number>; weather_adds_skill: boolean; period: { test: string } };
type TR = { tiles: Record<TileName, { held_out: TrackSummary | null; live: Live | null;
  community: Community | null }>; odor?: Odor | null };

/** "When we said about X%, it happened Y% of the time": paired bars per probability band. */
function Reliability({ bins }: { bins: NonNullable<TrackSummary["reliability"]> }) {
  return <figure className="reliability">
    <figcaption><strong>When we gave a chance, did it come true about that often?</strong></figcaption>
    <ul>{bins.map(b => <li key={b.predicted}>
      <span className="rel-label">We said {Math.round(b.predicted * 100)}%</span>
      <span className="rel-bars" aria-hidden><span className="rel-said" style={{ width: `${b.predicted * 100}%` }} /><span className="rel-real" style={{ width: `${b.observed * 100}%` }} /></span>
      <span className="rel-value">Happened {Math.round(b.observed * 100)}%</span></li>)}</ul>
    <p className="small muted">Held-out beach tests, grouped by the chance we gave. Grey: our chance. Teal: how often the beach actually failed.</p>
  </figure>;
}

function communityText(c: Community | null) {
  if (!c) return "Community reports: none yet.";
  const total = c.problem_reports + c.all_clear_reports;
  if (total < 5) return `Community reports: ${total} so far, too few to compare with the forecast.`;
  return `Community reports since ${c.since}: ${c.problem_on_elevated_days} of ${c.problem_rated} problem reports came on days we rated ` +
    `Moderate or higher, and ${c.all_clear_on_low_days} of ${c.all_clear_rated} all-clear reports came on Low days. ` +
    "Reports are from app users and are not verified.";
}
const fmt = (v: number | null | undefined) => (v === null || v === undefined ? "—" : Number.isInteger(v) ? String(v) : Math.abs(v) < 1 ? v.toFixed(3) : v.toFixed(1));

export default function TrackRecord() {
  const { placeId } = usePlace();
  const [tr, setTr] = useState<TR | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setErr(null);
    get<TR>("track-record.json", controller.signal).then(setTr).catch(e => { if (!controller.signal.aborted) setErr(e.message); });
    return () => controller.abort();
  }, [attempt]);
  return (
    <main className="wrap">
      <p className="small"><Link href={`/?place=${placeId ?? ""}`}>← Today</Link></p>
      <h1>Track record</h1>
      <p>Would you trust a forecast that never shows its homework? Each model was tested on years it never saw and compared
        with a simple guess. Every live forecast is saved and scored when the real answer comes in.</p>
      {err && <div className="error-panel" role="alert"><p>{err}</p><button className="secondary-button" onClick={() => setAttempt(x => x + 1)}>Try again</button></div>}
      {!tr && !err && <p role="status">Loading the forecast track record…</p>}
      {tr && TILE_ORDER.map((t) => {
        const s = tr.tiles[t].held_out, live = tr.tiles[t].live, community = tr.tiles[t].community;
        const baselines = [...new Set(s?.table.flatMap(row => Object.keys(row.baselines)) ?? [])];
        return (
          <section key={t} className="track-card">
            <h2>{TILE_LABEL[t]}</h2>
            {!s ? <p className="muted">No model released yet. The app shows live official data only.</p> : <>
              <p className={`track-verdict ${s.beats_baseline ? "good" : ""}`}>{s.beats_baseline ? "✓ Beats the simple guess" : "Does not beat the simple guess on every measure"}</p>
              <p style={{ fontWeight: 600 }}>{s.headline}</p>
              {s.reliability && s.reliability.length > 1 && <Reliability bins={s.reliability} />}
            </>}
            <p className="small muted">Live: {!live ? "no outcomes have arrived yet for forecasts made so far." :
              live.observed_fires !== undefined ? `since ${live.since}, ${live.observed_fires} new large fires county-wide vs ${live.expected_fires} expected.` :
              `${live.hits} of ${live.scored} scored forecasts matched what happened, since ${live.since}.`} {communityText(community)}</p>
            {s && <details>
              <summary>Technical details</summary>
              {s.note && <p className="small">{s.note}</p>}
              <p className="small muted">Test period {s.period}. {s.inputs}.{s.provisional ? " Provisional: border-flow history for recent years is not loaded yet." : ""}</p>
              <div className="table-scroll"><table>
                <caption className="sr-only">{TILE_LABEL[t]} model performance and baselines</caption>
                <thead><tr><th scope="col">Measure</th><th scope="col" className="num">Outlook SD</th>{baselines.map((b) => <th scope="col" key={b} className="num">{b}</th>)}</tr></thead>
                <tbody>{s.table.map((r) => (
                  <tr key={r.metric}><td>{r.metric}</td>
                    <td className="num">{fmt(r.model)}{r.model_ci95 ? <span className="muted"> ({fmt(r.model_ci95[0])}–{fmt(r.model_ci95[1])})</span> : null}</td>
                    {baselines.map((b) => <td key={b} className="num">{fmt(r.baselines[b])}</td>)}</tr>))}
                </tbody>
              </table></div>
              {s.replays?.map((rp) => (
                <div key={rp.name} style={{ marginTop: 12 }}>
                  <h3>Replay: {rp.name}</h3>
                  {rp.note && <p className="small">{rp.note}</p>}
                  {rp.days && <div className="table-scroll"><table>
                    <thead><tr><th>Day</th><th className="num">Observed peak</th><th className="num">Forecast</th><th className="num">High end</th><th className="num">Tide only</th></tr></thead>
                    <tbody>{rp.days.map((d) => (
                      <tr key={d.date}><td>{d.date}</td>{[d.observed, d.lvl_q50, d.lvl_q90, d.lvl_tide].map((v, i) => <td key={i} className="num">{(v - 3.79).toFixed(2)} ft</td>)}</tr>))}
                    </tbody>
                  </table></div>}
                  {rp.issued && <p className="small muted">Forecast issued {rp.issued} UTC; feet above MLLW. Minor flooding starts at 7.59 ft.</p>}
                </div>))}
            </details>}
          </section>
        );
      })}
      {tr?.odor && <section className="track-card">
        <h2>Sewage smell (South Bay): tested, not shipped</h2>
        <p style={{ fontWeight: 600 }}>{tr.odor.weather_adds_skill ? "Weather improved on recent complaints." :
          "Weather did not predict smell days better than simply looking at recent complaints, so the app shows the complaint record instead of a forecast."}</p>
        <p className="small muted">Tested on {tr.odor.test_days} days ({tr.odor.period.test}), {tr.odor.event_days} of them with 3 or more APCD odor complaints.
          Ranking score with recent complaints alone {tr.odor.auc.recent_reports.toFixed(2)}; adding weather {tr.odor.auc.recent_plus_weather.toFixed(2)}.</p>
      </section>}
    </main>
  );
}
