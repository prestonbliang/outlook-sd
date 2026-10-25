"use client";
import { useId, useMemo, useState } from "react";
import { Place, haversineKm } from "@/lib/api";

/** Search the named places (Census places + City of San Diego communities), or use the device location. */
export default function PlacePicker({ places, onPick }: { places: Place[]; onPick: (p: Place) => void }) {
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const id = useId();
  const [locating, setLocating] = useState(false);
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? places.filter((p) => p.name.toLowerCase().includes(s) || p.zip.startsWith(s)).slice(0, 8) : [];
  }, [q, places]);

  function locate() {
    if (!places.length) { setMsg("Neighborhoods are still loading. Please try again shortly."); return; }
    if (!navigator.geolocation) { setMsg("Location is not available in this browser."); return; }
    setMsg("Finding your location…");
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setLocating(false);
        const here = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        const best = places.reduce((a, b) => (haversineKm(here, a) <= haversineKm(here, b) ? a : b));
        if (haversineKm(here, best) > 30) { setMsg("You appear to be outside San Diego County. Pick a place instead."); return; }
        setMsg(null); onPick(best);
      },
      (error) => { setLocating(false); setMsg(error.code === 1 ? "Location permission was not given. Pick a place instead." : "Could not find your location. Search for a neighborhood instead."); },
      { timeout: 10000, maximumAge: 60000, enableHighAccuracy: false },
    );
  }

  return (
    <div className="place-picker">
      <label htmlFor={id} className="small" style={{ display: "block", fontWeight: 600 }}>Neighborhood or ZIP</label>
      <div className="place-picker-search">
        <input id={id} type="search" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" aria-controls={matches.length ? `${id}-results` : undefined}
               onKeyDown={event => { if (event.key === "Enter" && matches.length === 1) { event.preventDefault(); onPick(matches[0]); setQ(""); } }}
               placeholder="e.g. Imperial Beach or 92109" />
        <button onClick={locate} disabled={locating || !places.length} className="secondary-button">{locating ? "Locating…" : "Use my location"}</button>
      </div>
      {msg && <p className="small muted" role="status">{msg}</p>}
      {q.trim() && <p className="sr-only" role="status">{matches.length} matching neighborhoods shown. Tab to a result to choose it.</p>}
      {matches.length > 0 && (
        <ul id={`${id}-results`} className="place-results" aria-label="Matching neighborhoods">
          {matches.map((p) => (
            <li key={p.id}>
              <button onClick={() => { onPick(p); setQ(""); }} className="button-link">
                {p.name} <span className="muted">· {p.zip}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {q.trim() && matches.length === 0 && <p className="small muted">No San Diego County place matches “{q}”.</p>}
    </div>
  );
}
