"use client";
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { TileName } from "@/lib/api";
import { COVERAGE_LABEL, KIND_LABEL, KINDS, coverageFor, reportAge, summarizeObservations } from "@/lib/community";
import { REPORTS_CHANGED, availableReportKinds, ownReportOptions, reportManagementAvailable, sendReport, withdrawReportOption, type OwnReport } from "@/lib/reports";
import { useCommunity } from "@/lib/useCommunity";

export default function ReportBox({ tile, placeId, placeName }: { tile: TileName; placeId: string; placeName: string }) {
  const id = useId();
  const { data, error, refresh, enabled } = useCommunity(24);
  const summary = data?.find((r) => r.place_id === placeId && r.hazard === tile);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [supported, setSupported] = useState<string[] | null>(null);
  const [management, setManagement] = useState<boolean | null>(null);
  const [managementError, setManagementError] = useState<string | null>(null);
  const [managementAttempt, setManagementAttempt] = useState(0);
  const [own, setOwn] = useState<OwnReport[] | null>(null);
  const [ownError, setOwnError] = useState<string | null>(null);
  const ownRequest = useRef(0);
  const optionRefs = useRef(new Map<string, HTMLButtonElement>());
  const focusAfterRemoval = useRef<string | null>(null);
  useEffect(() => {
    if (!busy && focusAfterRemoval.current) {
      optionRefs.current.get(focusAfterRemoval.current)?.focus();
      focusAfterRemoval.current = null;
    }
  }, [busy]);
  const narrative = summary ? summarizeObservations(summary) : null;
  const refreshOwn = useCallback(async () => {
    const request = ++ownRequest.current;
    try {
      const rows = await ownReportOptions();
      if (request === ownRequest.current) { setOwn(rows); setOwnError(null); }
    } catch (e) { if (request === ownRequest.current) setOwnError((e as Error).message); }
  }, []);
  useEffect(() => {
    let active = true;
    if (enabled) {
      void availableReportKinds().then(kinds => { if (active) setSupported(kinds); });
      void reportManagementAvailable().then(available => { if (active) { setManagement(available); setManagementError(null); } })
        .catch(e => { if (active) setManagementError((e as Error).message); });
    }
    return () => { active = false; };
  }, [enabled, managementAttempt]);
  useEffect(() => {
    if (!management) return;
    const load = () => { void refreshOwn(); };
    load();
    window.addEventListener(REPORTS_CHANGED, load);
    window.addEventListener("focus", load);
    return () => { ++ownRequest.current; window.removeEventListener(REPORTS_CHANGED, load); window.removeEventListener("focus", load); };
  }, [management, refreshOwn]);
  const choices = KINDS[tile].filter(kind => supported?.includes(kind.kind));
  const mine = own?.filter(row => row.place_id === placeId && row.hazard === tile) ?? [];
  async function send(kind: string) {
    if (busy) return;
    setBusy(true); setStatus(null);
    try {
      await sendReport(placeId, tile, kind);
      setStatus({ ok: true, text: `Thanks. Your observation for ${placeName} was saved.` });
    } catch (e) { setStatus({ ok: false, text: (e as Error).message }); }
    finally { setBusy(false); }
  }
  async function remove(kind: string) {
    if (busy) return;
    setBusy(true); setStatus(null);
    try {
      await withdrawReportOption(placeId, kind);
      // Keep the successful change visible even if the subsequent owner-list refresh fails.
      setOwn(rows => rows?.filter(row => !(row.place_id === placeId && row.kind === kind)) ?? null);
      setStatus({ ok: true, text: "Your observation was removed from the community summary." });
      focusAfterRemoval.current = kind;
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
        {narrative && <section className="observation-summary" aria-label="Summary of recent observations">
          <h3>{narrative.headline}</h3><p>{narrative.detail}</p><p className="small muted">{narrative.evidence}</p>
        </section>}
        <p className="small">Report only what you observe here now. Tap an option to send it.
          {management && " Tap a selected option again, or use Remove below, to withdraw it."}</p>
        {managementError && <p className="small form-error" role="status">{managementError} <button className="button-link"
          onClick={() => { setManagementError(null); setManagementAttempt(n => n + 1); }}>Retry reporting safeguards</button></p>}
        {supported === null ? <p className="small muted" role="status">Loading observation options…</p> : <>
          <fieldset className="observation-group" disabled={busy || Boolean(managementError)} aria-busy={busy}>
            <legend>Conditions you noticed</legend>
            <div className="report-options">{choices.filter(k => k.problem).map(k =>
              <button key={k.kind} className="observation-button"
                ref={node => { if (node) optionRefs.current.set(k.kind, node); else optionRefs.current.delete(k.kind); }}
                aria-pressed={management ? mine.some(row => row.kind === k.kind) : undefined}
                onClick={() => mine.some(row => row.kind === k.kind) ? remove(k.kind) : send(k.kind)}>{k.label}
                {mine.some(row => row.kind === k.kind) && <span className="observation-selected" aria-hidden="true">✓</span>}</button>)}</div>
          </fieldset>
          <fieldset className="observation-group clear-observation" disabled={busy || Boolean(managementError)}>
            <legend>No concern noticed</legend>
            {choices.filter(k => !k.problem).map(k => <button key={k.kind} className="observation-button"
              ref={node => { if (node) optionRefs.current.set(k.kind, node); else optionRefs.current.delete(k.kind); }}
              aria-pressed={management ? mine.some(row => row.kind === k.kind) : undefined}
              onClick={() => mine.some(row => row.kind === k.kind) ? remove(k.kind) : send(k.kind)}>{k.label}
              {mine.some(row => row.kind === k.kind) && <span className="observation-selected" aria-hidden="true">✓</span>}</button>)}
          </fieldset>
        </>}
        {status && <p role={status.ok ? "status" : "alert"} className={status.ok ? "small" : "small form-error"}>{status.text}</p>}
        {management && <section className="own-observations" aria-labelledby={`${id}-own`}>
          <h3 id={`${id}-own`}>Your active observations</h3>
          {ownError ? <p className="small" role="status">{ownError} <button className="button-link" onClick={refreshOwn}>Retry your observations</button></p>
            : own === null ? <p className="small muted" role="status">Loading your observations…</p>
            : mine.length ? <ul>{mine.map(row => <li key={row.kind}>
              <span>{KIND_LABEL[row.kind]} <span className="small muted">{reportAge(row.created_at)}</span></span>
              <button className="button-link" disabled={busy} aria-label={`Remove ${KIND_LABEL[row.kind]}`}
                onClick={() => remove(row.kind)}>Remove</button>
            </li>)}</ul> : <p className="small muted">No active observations from this browser for this hazard here.</p>}
          <p className="small muted">Remove an accidental choice here within 24 hours, using the same browser and website. Removing it does not reset spam limits.
            Reports made before this feature was enabled cannot be recovered here.</p>
        </section>}
        {management === false && <p className="small muted">Report removal is unavailable on this connection. Older databases need the reporting update.</p>}
        {summary && <details className="observation-details"><summary>View observation counts</summary>
          <ul className="observation-counts small">{Object.entries(summary.kinds).map(([kind, n]) =>
            <li key={kind}>{KIND_LABEL[kind] ?? kind}: <strong>{n}</strong></li>)}</ul></details>}
      </>}
      <p className="small muted">Observations are unverified and never change the forecast. No reports does not mean no hazard.
        {tile === "water" && " Clear-looking water can still contain harmful bacteria; follow posted signs."}</p>
      <details className="report-safeguards"><summary>How reports are protected</summary>
        <p className="small muted">The database checks report types and neighborhoods, blocks the same choice for six hours,
          and limits each browser code to ten submissions per hour. Multiple choices are not independent confirmation.
          Clearing browser storage can bypass browser-based limits; this is not identity verification.</p>
        {management && <p className="small muted">Removal requires a private browser token; only its hash is stored in the database.
          Withdrawn reports leave public summaries but are retained for abuse limits. Administrators can hide abusive reports.</p>}
      </details>
      <p className="small muted">We store the neighborhood, report type, time, and a random browser code for repeat limits.
        No name or precise location. <Link href="/data/#community">How reports work</Link></p>
    </section>
  );
}
