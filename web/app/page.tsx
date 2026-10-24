"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import HazardRow from "@/components/HazardRow";
import PlacePicker from "@/components/PlacePicker";
import MapBoundary from "@/components/MapBoundary";
import { Outlook, TILE_NAME, TileName, get, updatedText } from "@/lib/api";
import { usePlace } from "@/lib/usePlace";

const HazardMap = dynamic(() => import("@/components/HazardMap"), { ssr: false });

export default function Today() {
  const { places, place, placeId, choose, error } = usePlace();
  const [outlook, setOutlook] = useState<Outlook | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [mapTile, setMapTile] = useState<TileName>("water");

  useEffect(() => {
    if (!placeId) return;
    const controller = new AbortController();
    setOutlook(null); setLoadError(null);
    get<Outlook>(`outlook/${placeId}.json`, controller.signal).then(setOutlook)
      .catch((e) => { if (!controller.signal.aborted) setLoadError(e.message); });
    return () => controller.abort();
  }, [placeId]);

  const q = `?place=${placeId ?? "downtown"}`;
  return (
    <div className="today">
      <main className="side">
        <div className="wrap">
          <header style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
            <h1 style={{ flex: 1 }}>{outlook?.place.name ?? place?.name ?? " "}</h1>
            <button className="button-link" onClick={() => setPicking(!picking)} aria-expanded={picking}>Change</button>
          </header>
          <p className="small muted" style={{ margin: "2px 0 0" }}>
            {outlook ? `${updatedText(outlook.updated_at)} · ZIP ${outlook.place.zip}` : "Loading forecast…"}
          </p>
          {(picking || error) && <PlacePicker places={places} onPick={(p) => { choose(p.id); setPicking(false); }} />}
          {(loadError || error) && <p role="alert">Could not load the forecast: {loadError ?? error}</p>}
          <div style={{ marginTop: 12, borderTop: "1px solid var(--rule)" }}>
            {outlook?.tiles.map((t) => (
              <HazardRow key={t.tile} tile={t} placeId={outlook.place.id} onSelect={() => setMapTile(t.tile)} />
            ))}
          </div>
          <nav className="nav" aria-label="More">
            <Link href={`/map/${q}&hazard=${mapTile}`}>Map & community</Link>
            <Link href={`/track-record/${q}`}>Track record</Link>
            <Link href={`/data/${q}`}>Data</Link>
          </nav>
          <p className="disclaimer">Outlook SD is a forecast, not an official advisory. Follow posted beach signs and official alerts.</p>
        </div>
      </main>
      <div className="mapcol">
        {place && <MapBoundary><HazardMap tile={mapTile} center={place} label={`${TILE_NAME[mapTile]} map around ${place.name}`} /></MapBoundary>}
      </div>
      <style>{`
        .mapcol { display: none; }
        @media (min-width: 1024px) {
          .today { display: grid; grid-template-columns: 420px 1fr; height: 100vh; }
          .side { background: var(--fog); overflow-y: auto; }
          .mapcol { display: block; position: relative; }
        }
      `}</style>
    </div>
  );
}
