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
import Icon from "@/components/Icon";
import { ELEVATED, Outlook, TILE_LABEL, TILE_NAME, TILE_ORDER, TileName, dayName, get, updatedText } from "@/lib/api";
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
  return <main className="home-page">
    <header className="home-hero">
      <div className="hero-copy">
        <p className="eyebrow"><span className="hero-line" /> Your San Diego outlook</p>
        <h1>Life happens outside.<span>Know what’s ahead.</span></h1>
        <p className="hero-description">Beach water, air, heat, coastal flooding and wildfire. A neighborhood view of the next few days, with context from the people who live here.</p>
        <div className="hero-actions"><a className="primary-link light-button" href="#local-outlook">See your local outlook <Icon name="arrow" size={18} /></a>
          <Link className="hero-text-link" href={`/map/${q}`}>Explore the map <Icon name="map" size={18} /></Link></div>
        <ul className="hero-signals" aria-label="Five environmental hazards">{TILE_ORDER.map(tile => <li key={tile}><Icon name={tile} size={16} />{TILE_NAME[tile]}</li>)}</ul>
      </div>
      <div className="hero-map-frame">
        <div className="neighborhood-heading">
          <div className="hero-place"><Icon name="pin" size={22} /><div><p className="eyebrow">Your neighborhood</p><h2>{place?.name ?? "Your neighborhood"}</h2>
            <p className="small muted">{place ? `ZIP ${place.zip} · San Diego County` : "Finding your neighborhood…"}</p></div></div>
          <button ref={changeButton} className="secondary-button" onClick={() => setPicking(!picking)} aria-expanded={picking} aria-controls="today-place-picker">Change place</button>
        </div>
        <div className="home-map-canvas">
          {desktopMap && place ? <MapBoundary><HazardMap tile={mapTile} center={place} places={places} onPlacePick={p => choose(p.id)} label={`${TILE_NAME[mapTile]} map around ${place.name}`} /></MapBoundary> : <div className="map-loading" role="status">Loading neighborhood map…</div>}
        </div>
        <div className="hero-map-caption"><span><Icon name={mapTile} size={16} />{TILE_LABEL[mapTile]} map</span>
          <Link href={`/map/${q}&hazard=${mapTile}`}>Open full {TILE_NAME[mapTile].toLowerCase()} map ↗</Link></div>
      </div>
    </header>
    {(picking || error) && <div id="today-place-picker" className="picker-panel home-picker"><PlacePicker places={places} onPick={p => { choose(p.id); setPicking(false); changeButton.current?.focus(); }} /></div>}
    <section className="home-outlook" aria-labelledby="local-outlook">
      <div className="section-heading"><div><p className="eyebrow">The neighborhood brief</p><h2 id="local-outlook">Your local outlook</h2>
        <p className="muted">Five signals. One place to make sense of them.</p></div>
        {outlook && <a className="planning-jump" href="#planning-heading">Open your three-day planning brief ↓</a>}</div>
      {(loadError || error) && <div className="error-panel" role="alert"><strong>Your outlook could not load.</strong>
        <p>{loadError ?? error}</p><button className="secondary-button" onClick={() => { retry(); setAttempt(x => x + 1); }}>Try again</button>
        <p className="small"><Link href={`/data/${q}`}>View official data sources</Link></p></div>}
      {outlook && <div className={`outlook-status ${!available || stale ? "notice" : ""}`}>
        <div className="outlook-refresh"><p className="small muted"><Icon name="clock" size={15} />{updatedText(outlook.updated_at)}</p><button className="button-link" onClick={() => setAttempt(x => x + 1)}>Refresh outlook</button></div>
        {!available ? <p>No forecasts are available for today. You can explore the map and check the official sources linked below.</p> :
          stale ? <p>Some forecasts use older or incomplete source data. Check the update times and official advisories.</p> : null}
        {(!available || stale) && <details><summary>How updates work</summary><p className="small muted">Refresh checks for a newer published snapshot. Official sources may update sooner.</p></details>}
      </div>}
      {!outlook && !loadError && !error && <div className="forecast-skeleton" role="status" aria-label="Loading five hazard forecasts">
        {["Water", "Air", "Heat", "Flood", "Fire"].map(name => <div key={name}><span>{name}</span><span className="skeleton-line" /></div>)}
      </div>}
      {together && <div className="compound-banner" role="note"><Icon name="shield" /><div><strong>{together.count === 2 ? "Two" : together.count} hazards at once {together.day}:</strong> {together.names}. Plan ahead.</div></div>}
      {outlook && <ul className="level-key" aria-label="Color key">{["low", "moderate", "high", "very_high"].map(l =>
        <li key={l}><span style={{ background: `var(--lvl-${l.replace("_", "-")})` }} />{{ low: "Low", moderate: "Moderate", high: "High", very_high: "Very high" }[l]}</li>)}
        <li className="muted">Tap a card for details</li></ul>}
      <div className="hazard-list">{outlook?.tiles.filter(t => !notConnected(t)).map(t => <HazardRow key={`${placeId}-${t.tile}`} tile={t} placeId={outlook.place.id}
        onSelect={() => setMapTile(t.tile)} coolZone={t.tile === "heat" || t.tile === "air" ? outlook.cool_zones?.[0] : undefined} />)}</div>
      {outlook?.tiles.filter(notConnected).map(t => <p key={t.tile} className="small muted not-connected">
        <Icon name="air" size={18} />{TILE_LABEL[t.tile]}: no forecast or observation is available in this snapshot. <a href={t.official_advisory.url}>Check AirNow for current air quality</a>.</p>)}
    </section>
    {outlook && <PlanningBrief outlook={outlook} />}
    <div className="home-personal">{place && <div className="personal-panel"><Watchlist places={places} selected={place} onPick={choose} /></div>}
      {outlook?.odor && <OdorCard odor={outlook.odor} place={outlook.place.name} />}</div>
    <section className="community-callout"><div className="community-emblem"><Icon name="community" size={34} /></div>
      <div><p className="eyebrow">A local view, made better together</p><h2>See something? Report it.</h2>
        <p>Share the conditions you’re already observing. Anonymous neighborhood reports add local context and never change the forecast.</p></div>
      <Link className="primary-link" href={`/map/${q}&hazard=${mapTile}#map-report`}>Report what you see <Icon name="arrow" size={18} /></Link>
    </section>
    <div className="home-principles"><div><Icon name="pin" /><h3>Local by design</h3><p>{places.length ? `${places.length} neighborhoods across San Diego County.` : "Neighborhood-level views across San Diego County."}</p></div>
      <div><Icon name="chart" /><h3>Open about accuracy</h3><p>See the models, their track record and their limits. <Link href={`/track-record/${q}`}>View the evidence ↗</Link></p></div>
      <div><Icon name="shield" /><h3>Context, not an all-clear</h3><p>Forecasts are not official advisories. Follow official alerts and posted signs.</p></div></div>
  </main>;
}
