"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import HazardRow from "@/components/HazardRow";
import PlacePicker from "@/components/PlacePicker";
import MapBoundary from "@/components/MapBoundary";
import Watchlist from "@/components/Watchlist";
import OdorCard from "@/components/OdorCard";
import PlanningBrief from "@/components/PlanningBrief";
import { ELEVATED, Outlook, TILE_LABEL, TILE_NAME, TileName, dayName, get, updatedText } from "@/lib/api";
import { currentDay, forecastDates, forecastState, localDate } from "@/lib/forecast";
import { usePlace } from "@/lib/usePlace";
import { useNow } from "@/lib/useNow";

const HazardMap = dynamic(() => import("@/components/HazardMap"), { ssr: false,
  loading: () => <div className="map-loading" role="status">Loading neighborhood map…</div> });

/** Air without a forecast or an observation gets an explicit snapshot-availability note. */
const notConnected = (t: Outlook["tiles"][number]) => t.tile === "air" && !t.days.length && !t.current;

/** First day (of the next three) when two or more hazards are High or worse at once. */
function compound(o: Outlook, now: number) {
  const dates = forecastDates(now);
  for (const date of dates) {
    const hit = o.tiles.filter(t => forecastState(t, now, date) === "current"
      && t.days.some(d => d.date === date && d.level && ELEVATED.has(d.level)));
    if (hit.length >= 2) return { day: date === localDate() ? "today" : `on ${dayName(date, "long")}`,
      count: hit.length, names: hit.map(t => TILE_LABEL[t.tile]).join(" and ") };
  }
  return null;
}

export default function Today() {
  const now = useNow();
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
  const together = outlook ? compound(outlook, now) : null;
  return <div className="today">
    <main className="side">
      <div className="wrap today-content">
        <p className="eyebrow">Today and the next 3 days</p>
        <header className="neighborhood-heading">
          <div><h1>{place?.name ?? "Your neighborhood"}</h1><p className="small muted">{place ? `ZIP ${place.zip} · Local outlook` : "Finding your neighborhood…"}</p></div>
          <button ref={changeButton} className="secondary-button" onClick={() => setPicking(!picking)} aria-expanded={picking} aria-controls="today-place-picker">Change place</button>
        </header>
        <p className="outlook-intro">What will the ocean, air, heat, tides and fire do near you this week? Forecasts for your neighborhood,
          each one checked every day against what really happened.</p>
        {(picking || error) && <div id="today-place-picker" className="picker-panel"><PlacePicker places={places} onPick={p => { choose(p.id); setPicking(false); changeButton.current?.focus(); }} /></div>}
        {(loadError || error) && <div className="error-panel" role="alert"><strong>Your outlook could not load.</strong>
          <p>{loadError ?? error}</p><button className="secondary-button" onClick={() => { retry(); setAttempt(x => x + 1); }}>Try again</button>
          <p className="small"><Link href={`/data/${q}`}>View official data sources</Link></p></div>}
        {outlook && <div className={`outlook-status ${!available || stale ? "notice" : ""}`}>
          <div className="outlook-refresh"><p className="small muted">{updatedText(outlook.updated_at)}</p><button className="button-link" onClick={() => setAttempt(x => x + 1)}>Refresh outlook</button></div>
          {!available ? <p>No forecasts are available for today. You can explore the map and check the official sources linked below.</p> :
            stale ? <p>Some forecasts use older or incomplete source data. Check the update times and official advisories.</p> : null}
          {(!available || stale) && <p className="small muted">Refresh checks for a newer published snapshot. Official sources may update sooner.</p>}
        </div>}
        {!outlook && !loadError && !error && <div className="forecast-skeleton" role="status" aria-label="Loading five hazard forecasts">
          {["Water", "Air", "Heat", "Flood", "Fire"].map(name => <div key={name}><span>{name}</span><span className="skeleton-line" /></div>)}
        </div>}
        {together && <div className="compound-banner" role="note"><strong>{together.count === 2 ? "Two" : together.count} hazards at once {together.day}:</strong> {together.names}. Plan ahead.</div>}
        {outlook && <a className="planning-jump" href="#planning-heading">Open your three-day planning brief ↓</a>}
        {outlook && <ul className="level-key" aria-label="Color key">{["low", "moderate", "high", "very_high"].map(l =>
          <li key={l}><span style={{ background: `var(--lvl-${l.replace("_", "-")})` }} />{{ low: "Low", moderate: "Moderate", high: "High", very_high: "Very high" }[l]}</li>)}
          <li className="muted">Tap a row for details</li></ul>}
        <div className="hazard-list">{outlook?.tiles.filter(t => !notConnected(t)).map(t => <HazardRow key={`${placeId}-${t.tile}`} tile={t} placeId={outlook.place.id}
          onSelect={() => setMapTile(t.tile)} coolZone={t.tile === "heat" || t.tile === "air" ? outlook.cool_zones?.[0] : undefined} />)}</div>
        {outlook?.tiles.filter(notConnected).map(t => <p key={t.tile} className="small muted not-connected">
          {TILE_LABEL[t.tile]}: no forecast or observation is available in this snapshot. <a href={t.official_advisory.url}>Check AirNow for current air quality</a>.</p>)}
        {outlook && <PlanningBrief outlook={outlook} />}
        {outlook?.odor && <OdorCard odor={outlook.odor} place={outlook.place.name} />}
        {place && <Watchlist places={places} selected={place} onPick={choose} />}
        <div className="community-callout"><h2>See something? Report it.</h2>
          <p className="small muted">Brown water, smoke, a flooded street: tap what you see. Reports are anonymous and are compared with our forecasts.</p>
          <Link className="primary-link" href={`/map/${q}&hazard=${mapTile}#map-report`}>Report what you see →</Link></div>
        <p className="disclaimer">Outlook SD is a forecast, not an official advisory. Follow posted beach signs and official alerts.</p>
      </div>
    </main>
    <div className="mapcol">
      {desktopMap && place && <MapBoundary><HazardMap tile={mapTile} center={place} places={places} onPlacePick={p => choose(p.id)} label={`${TILE_NAME[mapTile]} map around ${place.name}`} /></MapBoundary>}
      <Link className="open-map-link" href={`/map/${q}&hazard=${mapTile}`}>Open full {TILE_NAME[mapTile].toLowerCase()} map ↗</Link>
    </div>
  </div>;
}
