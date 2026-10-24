"use client";
import { useMemo, useState } from "react";
import { Place, haversineKm } from "@/lib/api";

/** Search the named places (Census places + City of San Diego communities), or use the device location. */
export default function PlacePicker({ places, onPick }: { places: Place[]; onPick: (p: Place) => void }) {
  const [q, setQ] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? places.filter((p) => p.name.toLowerCase().includes(s) || p.zip.startsWith(s)).slice(0, 8) : [];
  }, [q, places]);

  function locate() {
    if (!navigator.geolocation) { setMsg("Location is not available in this browser."); return; }
    setMsg("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const here = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        const best = places.reduce((a, b) => (haversineKm(here, a) <= haversineKm(here, b) ? a : b));
        if (haversineKm(here, best) > 30) { setMsg("You appear to be outside San Diego County. Pick a place instead."); return; }
        setMsg(null); onPick(best);
      },
      () => setMsg("Location permission was not given. Pick a place instead."),
    );
  }

  return (
    <div style={{ padding: "8px 0 12px" }}>
      <label htmlFor="place-search" className="small" style={{ display: "block", fontWeight: 600 }}>Neighborhood or ZIP</label>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input id="place-search" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off"
               placeholder="e.g. Imperial Beach or 92109"
               style={{ flex: "1 1 200px", font: "inherit", padding: "8px 10px", border: "1px solid var(--slate)", borderRadius: 2 }} />
        <button onClick={locate} style={{ padding: "8px 12px", border: "1px solid var(--signal)", background: "var(--paper)",
                color: "var(--signal)", borderRadius: 2, cursor: "pointer" }}>Use my location</button>
      </div>
      {msg && <p className="small muted" role="status">{msg}</p>}
      {matches.length > 0 && (
        <ul style={{ listStyle: "none", margin: "4px 0 0", padding: 0, border: "1px solid var(--rule)" }}>
          {matches.map((p) => (
            <li key={p.id}>
              <button onClick={() => { onPick(p); setQ(""); }} className="button-link"
                      style={{ display: "block", width: "100%", textAlign: "left", padding: "8px 10px", textDecoration: "none" }}>
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
