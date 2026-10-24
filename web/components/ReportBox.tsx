"use client";
import { useEffect, useState } from "react";
import { TileName } from "@/lib/api";
import { Count, KINDS, KIND_LABEL, reportCounts, reportsEnabled, sendReport } from "@/lib/reports";

/** One-tap community report for this place and hazard, plus the last 7 days of reports here. */
export default function ReportBox({ tile, placeId, placeName }: { tile: TileName; placeId: string; placeName: string }) {
  const [counts, setCounts] = useState<Count[] | null>(null);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => reportCounts(7).then((c) => setCounts(c.filter((x) => x.place_id === placeId && x.hazard === tile)))
    .catch(() => setCounts(null));
  useEffect(() => { if (reportsEnabled) load(); }, [placeId, tile]); // eslint-disable-line react-hooks/exhaustive-deps

  async function send(kind: string) {
    setBusy(true); setStatus(null);
    try {
      await sendReport(placeId, tile, kind);
      setStatus({ ok: true, text: `Thanks. Your report for ${placeName} is counted below.` });
      load();
    } catch (e) {
      setStatus({ ok: false, text: (e as Error).message });
    } finally { setBusy(false); }
  }

  const totals = new Map<string, number>();
  counts?.forEach((c) => totals.set(c.kind, (totals.get(c.kind) ?? 0) + c.n));
  return (
    <section aria-labelledby="report-h" style={{ borderTop: "1px solid var(--rule)", marginTop: 20, paddingTop: 12 }}>
      <h2 id="report-h">What do you see in {placeName}?</h2>
      {tile === "fire" && <p style={{ fontWeight: 600 }}>If you see a new fire, call 911 first.</p>}
      {!reportsEnabled ? <p className="small muted">Community reports are not connected on this copy of the app.</p> : <>
        <p className="small muted">One tap. We store only the neighborhood, the report type and the time — no name, no exact location. Reports are from app users and are not checked by officials.</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {KINDS[tile].map((k) => (
            <button key={k.kind} disabled={busy} onClick={() => send(k.kind)}
                    style={{ padding: "8px 12px", border: "1px solid var(--signal)", background: "var(--paper)", color: "var(--signal)",
                             borderRadius: 2, cursor: busy ? "wait" : "pointer" }}>{k.label}</button>
          ))}
        </div>
        {status && <p role="status" className="small" style={{ color: status.ok ? "var(--ink)" : "var(--lvl-high)" }}>{status.text}</p>}
        <p className="small" style={{ marginBottom: 0 }}>
          Reports here, last 7 days: {totals.size === 0 ? "none yet." :
            [...totals.entries()].map(([k, n]) => `${KIND_LABEL[k]} ${n}`).join(" · ")}
        </p>
      </>}
    </section>
  );
}
