"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import HazardRow from "@/components/HazardRow";
import PlacePicker from "@/components/PlacePicker";
import MapBoundary from "@/components/MapBoundary";
import Watchlist from "@/components/Watchlist";
import { Outlook, TILE_NAME, TileName, get, updatedText } from "@/lib/api";
import { currentDay, forecastState } from "@/lib/forecast";
import { usePlace } from "@/lib/usePlace";

const HazardMap = dynamic(() => import("@/components/HazardMap"), { ssr: false,
  loading: () => <div className="map-loading" role="status">Loading neighborhood map…</div> });

export default function Today() {
  const { places, place, placeId, choose, error, retry } = usePlace();
  const [outlook, setOutlook] = useState<Outlook | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [mapTile, setMapTile] = useState<TileName>("water");
  const [attempt, setAttempt] = useState(0);
  const [desktopMap, setDesktopMap] = useState(false);
  const changeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const media = window.matchMedia("(min-width: 1024px)");
    const update = () => setDesktopMap(media.matches);
    update(); media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!placeId) return;
    const controller = new AbortController();
    setOutlook(null); setLoadError(null);
    get<Outlook>(`outlook/${placeId}.json`, controller.signal).then(setOutlook)
      .catch(e => { if (!controller.signal.aborted) setLoadError(e.message); });
    return () => controller.abort();
  }, [placeId, attempt]);
  const q = `?place=${placeId ?? "downtown"}`;
  const available = outlook?.tiles.filter(t => currentDay(t)).length ?? 0;
  const stale = outlook?.tiles.some(t => forecastState(t) === "stale");
  return <div className="today">
    <main className="side">
      <div className="wrap today-content">
        <p className="eyebrow">San Diego County · Today + 3 days</p>
        <header className="neighborhood-heading">
          <div><h1>{place?.name ?? "Your neighborhood"}</h1><p className="small muted">{place ? `ZIP ${place.zip} · Local outlook` : "Finding your neighborhood…"}</p></div>
          <button ref={changeButton} className="secondary-button" onClick={() => setPicking(!picking)} aria-expanded={picking} aria-controls="today-place-picker">Change place</button>
        </header>
        <p className="outlook-intro">Plan your day with local forecasts for beach water, air, heat, coastal flooding, and fire. Explore the map and share conditions you observe nearby.</p>
        {(picking || error) && <div id="today-place-picker" className="picker-panel"><PlacePicker places={places} onPick={p => { choose(p.id); setPicking(false); changeButton.current?.focus(); }} /></div>}
        {place && <Watchlist places={places} selected={place} onPick={choose} />}
        {(loadError || error) && <div className="error-panel" role="alert"><strong>Your outlook could not load.</strong>
          <p>{loadError ?? error}</p><button className="secondary-button" onClick={() => { retry(); setAttempt(x => x + 1); }}>Try again</button>
          <p className="small"><Link href={`/data/${q}`}>View official data sources</Link></p></div>}
        {outlook && <div className={`outlook-status ${!available || stale ? "notice" : ""}`}>
          <div className="outlook-refresh"><p className="small muted">{updatedText(outlook.updated_at)}</p><button className="button-link" onClick={() => setAttempt(x => x + 1)}>Refresh outlook</button></div>
          {!available ? <p>No forecasts are available for today. You can explore the map and check the official sources linked below.</p> :
            stale ? <p>Some forecasts use older or incomplete source data. Check the update times and official advisories.</p> : <p className="small">Five perspectives on the places you care about.</p>}
        </div>}
        {!outlook && !loadError && !error && <div className="forecast-skeleton" role="status" aria-label="Loading five hazard forecasts">
          {["Water", "Air", "Heat", "Flood", "Fire"].map(name => <div key={name}><span>{name}</span><span className="skeleton-line" /></div>)}
        </div>}
        <div className="hazard-list">{outlook?.tiles.map(t => <HazardRow key={`${placeId}-${t.tile}`} tile={t} placeId={outlook.place.id} onSelect={() => setMapTile(t.tile)} />)}</div>
        <div className="community-callout"><span className="eyebrow">Your view matters</span><h2>Help your neighborhood see the full picture.</h2>
          <p className="small muted">Share what you observe, see recent reports, and discover where more observations are needed.</p>
          <Link className="primary-link" href={`/map/${q}&hazard=${mapTile}#map-report`}>Explore map & contribute →</Link></div>
        <p className="disclaimer">Outlook SD is a forecast, not an official advisory. Follow posted beach signs and official alerts.</p>
      </div>
    </main>
    <div className="mapcol">
      {desktopMap && place && <MapBoundary><HazardMap tile={mapTile} center={place} places={places} onPlacePick={p => choose(p.id)} label={`${TILE_NAME[mapTile]} map around ${place.name}`} /></MapBoundary>}
      <Link className="open-map-link" href={`/map/${q}&hazard=${mapTile}`}>Open full {TILE_NAME[mapTile].toLowerCase()} map ↗</Link>
    </div>
  </div>;
}
