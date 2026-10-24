"use client";
import Link from "next/link";
import { useId, useState } from "react";
import type { TileName } from "@/lib/api";
import { COVERAGE_LABEL, KIND_LABEL, KINDS, coverageFor, reportAge } from "@/lib/community";
import { sendReport } from "@/lib/reports";
import { useCommunity } from "@/lib/useCommunity";

export default function ReportBox({ tile, placeId, placeName }: { tile: TileName; placeId: string; placeName: string }) {
  const id = useId();
  const { data, error, refresh, enabled } = useCommunity(24);
  const summary = data?.find((r) => r.place_id === placeId && r.hazard === tile);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  async function send(kind: string) {
    if (busy) return;
    setBusy(true); setStatus(null);
    try {
      await sendReport(placeId, tile, kind);
      setStatus({ ok: true, text: `Thanks. Your observation for ${placeName} was saved.` });
    } catch (e) { setStatus({ ok: false, text: (e as Error).message }); }
    finally { setBusy(false); }
  }
  return (
    <section className="report-box" aria-labelledby={id}>
      <p className="eyebrow">Community observations</p>
      <h2 id={id}>What do you see in {placeName}?</h2>
      {tile === "fire" && <p className="notice">If you see a new fire, call 911 first. This form does not contact emergency services.</p>}
      {!enabled ? <p className="small muted">Community reporting is not connected yet. You can still explore the map and official sources.</p> : <>
        {error ? <p role="status" className="small">{error} <button className="button-link" onClick={refresh}>Retry</button></p> :
          data === null ? <p className="small muted" role="status">Loading recent observations…</p> :
          <div className={`coverage-note coverage-${coverageFor(summary)}`}>
            <strong>{COVERAGE_LABEL[coverageFor(summary)]}</strong>
            <p className="small">{summary ? `${summary.total} observation${summary.total === 1 ? "" : "s"} from ${summary.reporters} browser${summary.reporters === 1 ? "" : "s"} in the past 24 hours. Latest: ${reportAge(summary.last_report_at)}.` :
              "This neighborhood is a reporting blind spot for this hazard in the past 24 hours."}
              {coverageFor(summary) !== "reported" && " If you are already here, help fill the gap with what you observe."}</p>
          </div>}
        <p className="small">Report only what you observe here now. Choose one:</p>
        <div className="report-options" aria-busy={busy}>
          {KINDS[tile].map((k) => <button key={k.kind} className="observation-button" disabled={busy}
            onClick={() => send(k.kind)}>{k.label}</button>)}
        </div>
        {status && <p role={status.ok ? "status" : "alert"} className={status.ok ? "small" : "small form-error"}>{status.text}</p>}
        {summary && <ul className="observation-counts small">{Object.entries(summary.kinds).map(([kind, n]) =>
          <li key={kind}>{KIND_LABEL[kind] ?? kind}: <strong>{n}</strong></li>)}</ul>}
      </>}
      <p className="small muted">Observations are unverified and never change the forecast. No reports does not mean no hazard.
        {tile === "water" && " Clear-looking water can still contain harmful bacteria; follow posted signs."}</p>
      <p className="small muted">We store the neighborhood, report type, time, and a random browser code for repeat limits.
        No name or precise location. <Link href="/data/#community">How reports work</Link></p>
    </section>
  );
}
