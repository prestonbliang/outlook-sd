"use client";
import { useEffect, useState } from "react";
import { get, updatedText } from "@/lib/api";
import { localDate } from "@/lib/forecast";
import { useCommunity } from "@/lib/useCommunity";
import { useNow } from "@/lib/useNow";

interface Manifest { schema_version: number; generated_at: string; forecast_date: string; source_commit: string | null }
export default function SnapshotStatus() {
  const now = useNow();
  const community = useCommunity(24);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setError(false);
    get<Manifest>("build.json", controller.signal).then(value => {
      if (value.schema_version !== 1 || !Number.isFinite(Date.parse(value.generated_at)) || !/^\d{4}-\d{2}-\d{2}$/.test(value.forecast_date))
        throw new Error("Invalid deployment metadata");
      setManifest(value);
    }).catch(() => { if (!controller.signal.aborted) { setManifest(null); setError(true); } });
    return () => controller.abort();
  }, [attempt]);
  const age = manifest ? now - Date.parse(manifest.generated_at) : NaN;
  const older = manifest && (age > 6 * 3600000 || age < -300000 || manifest.forecast_date !== localDate(new Date(now)));
  return <section className="snapshot-status" aria-labelledby="snapshot-heading">
    <h2 id="snapshot-heading">What is connected?</h2>
    <p className="small"><strong>Forecast snapshot:</strong> {error ? "Publication details could not load." : !manifest ? "Loading publication details…" :
      `${updatedText(manifest.generated_at)}. ${older ? "This snapshot needs updating; use the official sources for current conditions." : "Source freshness still varies by hazard; check the times below."}`}
      {error && <> <button className="button-link" onClick={() => setAttempt(x => x + 1)}>Retry publication check</button></>}</p>
    <p className="small"><strong>Community observations:</strong> {!community.enabled ? "Reporting is not connected in this deployment." : community.error
      ? <>Live observations could not load. <button className="button-link" onClick={community.refresh}>Retry community connection</button></> :
      community.data === null ? "Checking the live reporting connection…" :
        `Live connection verified. ${community.data.reduce((n, s) => n + s.total, 0)} observations in the past 24 hours.`}</p>
    <p className="small muted">Forecasts come from the published snapshot. Community observations load separately from the reporting database.
      New reports never change a forecast or confirm an area is safe.</p>
    {manifest && <details><summary>Publication details</summary><dl className="publication-details">
      <dt>Forecast date (Pacific)</dt><dd>{manifest.forecast_date}</dd>
      <dt>Published (Pacific)</dt><dd>{new Date(manifest.generated_at).toLocaleString("en-US", { timeZone: "America/Los_Angeles" })} PT</dd>
      <dt>Source revision</dt><dd>{manifest.source_commit && /^[a-f0-9]{7,40}$/i.test(manifest.source_commit) ? <code>{manifest.source_commit.slice(0, 7)}</code> : "Not recorded by this build"}</dd>
    </dl></details>}
  </section>;
}
