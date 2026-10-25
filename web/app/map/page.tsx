"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import LevelBadge from "@/components/LevelBadge";
import MapBoundary from "@/components/MapBoundary";
import PlacePicker from "@/components/PlacePicker";
import ReportBox from "@/components/ReportBox";
import Watchlist from "@/components/Watchlist";
import ForecastStatus from "@/components/ForecastStatus";
import { dateLabel, localDate } from "@/lib/forecast";
import { AQI_HEX, LEVEL_HEX, LEVEL_WORD, TILE_NAME, TILE_ORDER, Outlook, TileName, dayName, get } from "@/lib/api";
import { COVERAGE_LABEL, coverageFor, reportAge } from "@/lib/community";
import { useCommunity } from "@/lib/useCommunity";
import { usePlace } from "@/lib/usePlace";
import { useNow } from "@/lib/useNow";
import PageIntro from "@/components/PageIntro";
import Icon from "@/components/Icon";

const HazardMap = dynamic(() => import("@/components/HazardMap"), {
  ssr: false, loading: () => <div className="map-loading" role="status">Loading San Diego map…</div>,
});
const NOTES: Record<TileName, string> = {
  water: "Monitored beach stations: predicted chance of bacteria above the state standard. Appearance alone cannot establish water quality.",
  air: "Monitor locations: daily AQI forecasts, or current readings when today's forecast is unavailable.",
  heat: "ZIP areas: the Outlook SD model in City Fire-Rescue ZIPs; state CalHeatScore elsewhere. Gray means no rating.",
  flood: "Coastal outlines share one San Diego Bay gauge forecast. These are approximate shoreline areas, not street-level flood predictions.",
  fire: "2 km areas: relative risk of a new fire growing beyond 10 acres. Dark dots are active incidents, shown for today only.",
};

export default function MapPage() {
  const now = useNow();
  const today = localDate(new Date(now || Date.now()));
  const { places, place, placeId, choose, error: placeError, retry } = usePlace();
  const [tile, setTile] = useState<TileName>("water");
  const [dates, setDates] = useState<string[]>([]);
  const [date, setDate] = useState<string>();
  const [dateError, setDateError] = useState(false);
  const [dateAttempt, setDateAttempt] = useState(0);
  const [shareMessage, setShareMessage] = useState<string | null>(null);
  const [shareURL, setShareURL] = useState<string | null>(null);
  const [hours, setHours] = useState(24);
  const [showReports, setShowReports] = useState(true);
  const [showCoverage, setShowCoverage] = useState(false);
  const [onlyGaps, setOnlyGaps] = useState(false);
  const [search, setSearch] = useState("");
  const [outlook, setOutlook] = useState<Outlook | null>(null);
  const [outlookError, setOutlookError] = useState<string | null>(null);
  const [outlookAttempt, setOutlookAttempt] = useState(0);
  const community = useCommunity(hours);
  useEffect(() => {
    // Report links can arrive before the selected neighborhood exists in the DOM.
    if (place && window.location.hash === "#map-report") {
      const frame = requestAnimationFrame(() => document.getElementById("map-report")?.scrollIntoView({ block: "start", behavior: "instant" }));
      return () => cancelAnimationFrame(frame);
    }
  }, [place]);
  useEffect(() => {
    if (!new URLSearchParams(window.location.search).get("date") && dates.includes(today)) setDate(today);
  }, [today, dates]);
  useEffect(() => {
    const controller = new AbortController();
    setDateError(false);
    function sync(validDates: string[]) {
      const params = new URLSearchParams(window.location.search);
      const selected = params.get("hazard") as TileName;
      setTile(TILE_ORDER.includes(selected) ? selected : "water");
      const requested = params.get("date");
      setDate(requested && validDates.includes(requested) ? requested : validDates.includes(localDate()) ? localDate() : validDates[0]);
      setHours(params.get("reports") === "168" ? 168 : 24);
    }
    get<{ dates: string[] }>("map/dates.json", controller.signal).then(d => {
      if (!d.dates?.length || d.dates.some(date => !/^\d{4}-\d{2}-\d{2}$/.test(date))) throw new Error("Invalid map dates");
      setDates(d.dates); sync(d.dates);
    }).catch(() => { if (!controller.signal.aborted) setDateError(true); });
    return () => controller.abort();
  }, [dateAttempt]);
  // Back/forward must restore hazard/day controls as well as the selected neighborhood.
  useEffect(() => {
    function restore() {
      const params = new URLSearchParams(window.location.search);
      const hazard = params.get("hazard") as TileName;
      setTile(TILE_ORDER.includes(hazard) ? hazard : "water");
      const requested = params.get("date");
      setDate(requested && dates.includes(requested) ? requested : dates.includes(localDate()) ? localDate() : dates[0]);
      setHours(params.get("reports") === "168" ? 168 : 24);
    }
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [dates]);
  useEffect(() => {
    if (!placeId) return;
    const controller = new AbortController();
    setOutlook(null); setOutlookError(null);
    get<Outlook>(`outlook/${placeId}.json`, controller.signal).then(setOutlook)
      .catch((e) => { if (!controller.signal.aborted) setOutlookError(e.message); });
    return () => controller.abort();
  }, [placeId, outlookAttempt]);
  function selectTile(t: TileName) {
    setTile(t);
    const url = new URL(window.location.href); url.searchParams.set("hazard", t);
    window.history.pushState(null, "", url);
  }
  function selectDate(value: string) {
    setDate(value); const url = new URL(window.location.href); url.searchParams.set("date", value);
    window.history.pushState(null, "", url);
  }
  async function share() {
    const url = new URL("/map/", window.location.origin);
    url.searchParams.set("place", placeId ?? "downtown"); url.searchParams.set("hazard", tile);
    if (date) url.searchParams.set("date", date);
    url.searchParams.set("reports", String(hours));
    setShareURL(url.href);
    try { await navigator.clipboard.writeText(url.href); setShareMessage("Link copied with this neighborhood, hazard, and forecast day."); }
    catch { setShareMessage("Copy this link to share the current view."); }
  }
  const eligible = useMemo(() => places.filter((p) => tile !== "water" || p.coastal), [places, tile]);
  const byPlace = useMemo(() => new Map(community.data?.filter((s) => s.hazard === tile).map((s) => [s.place_id, s])), [community.data, tile]);
  const gaps = eligible.filter((p) => coverageFor(byPlace.get(p.id)) !== "reported");
  const shown = eligible.filter((p) => (!onlyGaps || !community.data || coverageFor(byPlace.get(p.id)) !== "reported") &&
    (!search.trim() || `${p.name} ${p.zip}`.toLowerCase().includes(search.trim().toLowerCase())));
  const current = outlook?.tiles.find((t) => t.tile === tile);
  const forecast = current?.days.find((d) => d.date === date && d.value !== null);
  const legend = tile === "air" ? AQI_HEX : LEVEL_HEX;
  const windowLabel = hours === 24 ? "24 hours" : "7 days";
  return (
    <main className="map-page">
      <PageIntro eyebrow="The county, in context" title="Explore your neighborhood" description="Look closer. Follow the forecasts, explore your surroundings, and see what people nearby are noticing." icon="map">
        {place && <a className="primary-link" href="#map-report">Report a condition <Icon name="community" size={17} /></a>}
        <button className="secondary-button" onClick={share} disabled={!placeId}>Share this view ↗</button>
      </PageIntro>
      {shareMessage && <div className="share-panel"><p role="status" className="small">{shareMessage}</p>
        <label className="sr-only" htmlFor="share-url">Link to this map view</label><input id="share-url" readOnly value={shareURL ?? ""} onFocus={event => event.target.select()} /></div>}
      {dates.length > 0 && dates[0] !== localDate() && <p className="notice" role="status">This map uses an older forecast snapshot. Check the date and official sources before making plans.</p>}
      <fieldset className="hazard-switcher">
        <legend className="sr-only">Choose a hazard</legend>
        {TILE_ORDER.map((t) => <label key={t} className={tile === t ? "hazard-option selected" : "hazard-option"}>
          <input type="radio" name="hazard" checked={tile === t} onChange={() => selectTile(t)} /><Icon name={t} size={19} />{TILE_NAME[t]}</label>)}
      </fieldset>
      <div className="explorer-grid">
        <aside className="explorer-sidebar" aria-label="Map controls and observations">
          <div className="explorer-panel">
            <h2>Find a place</h2>
            <PlacePicker places={places} onPick={(p) => choose(p.id)} />
            {place && <Watchlist places={places} selected={place} onPick={choose} />}
            {placeError && <p role="alert">Neighborhoods could not load: {placeError} <button className="button-link" onClick={retry}>Try again</button></p>}
            <fieldset className="day-switcher"><legend>Forecast day</legend>
              {dates.map(d => <label key={d} className={date === d ? "day-option selected" : "day-option"}>
                <input type="radio" name="forecast-day" checked={date === d} onChange={() => selectDate(d)} />
                {dateLabel(d)}</label>)}
            </fieldset>
            {dateError && <p role="status" className="small">Forecast dates are unavailable. Check the layer's update time. <button className="button-link" onClick={() => setDateAttempt(x => x + 1)}>Try again</button></p>}
            <p className="small muted">{NOTES[tile]}</p>
          </div>
          <div className="explorer-panel">
            <p className="eyebrow">Help fill the gaps</p><h2>Community coverage</h2>
            <p className="small">A blind spot means we need more observations here. It does not mean the area has lower risk.</p>
            {!community.enabled ? <p className="notice small">Community reporting is not connected yet. Coverage is unknown.</p> : <>
              <label className="small field-label" htmlFor="report-window">Observations from the past</label>
              <select id="report-window" value={hours} onChange={e => {
                setHours(Number(e.target.value)); const url = new URL(window.location.href); url.searchParams.set("reports", e.target.value);
                window.history.pushState(null, "", url);
              }}>
                <option value={24}>24 hours</option><option value={168}>7 days</option>
              </select>
              {community.error ? <p role="status" className="small">{community.error} <button className="button-link" onClick={community.refresh}>Retry</button></p> :
                community.data === null ? <p role="status" className="small">Loading coverage…</p> : <>
                  <p className="coverage-stat"><strong>{gaps.length}</strong> of {eligible.length} neighborhoods need more observations.</p>
                  <label className="check-option"><input type="checkbox" checked={showReports} onChange={(e) => setShowReports(e.target.checked)} />Show community observations</label>
                  <label className="check-option"><input type="checkbox" checked={showCoverage} onChange={(e) => setShowCoverage(e.target.checked)} />Highlight reporting blind spots</label>
                  <label className="check-option"><input type="checkbox" checked={onlyGaps} onChange={(e) => setOnlyGaps(e.target.checked)} />List only areas needing reports</label>
                  <p className="small muted">Coverage goal: observations from at least 3 browsers per neighborhood and hazard in the selected window. Browser counts are not verified people.</p>
                </>}
              <p className="small muted">Reports describe the past {windowLabel}, even when a future forecast day is selected. Observations never change a forecast.</p>
            </>}
          </div>
        </aside>
        <div className="explorer-main">
          <div className="explorer-map">
            <MapBoundary><HazardMap tile={tile} date={date} center={place ?? undefined} places={places} observationsOnPage onPlacePick={(p) => choose(p.id)}
              summaries={community.data} showReports={showReports} showCoverage={showCoverage} /></MapBoundary>
          </div>
          <ul aria-label="Map legend" className="map-legend">
            {Object.entries(legend).map(([key, hex]) => <li key={key}><span aria-hidden style={{ background: hex }} />{LEVEL_WORD[key]}</li>)}
            <li><span aria-hidden style={{ background: "#D5DCE3" }} />No rating</li>
            {community.data && showCoverage && <li><span className="gap-key" aria-hidden />More reports needed</li>}
            {community.data && showReports && <li>Community circles: dark = more problem reports; white = equal or more clear observations. Tap for counts.</li>}
          </ul>
          <p className="small muted">Tap a station, shaded area, or neighborhood circle to inspect it. You can also select a neighborhood below.</p>
          {place && <section className="selected-neighborhood" id="map-report" tabIndex={-1} aria-label="Selected neighborhood">
            <div className="selected-heading"><div className="selected-context"><Icon name={tile} size={24} /><div><p className="eyebrow">Selected neighborhood · ZIP {place.zip}</p><h2>{place.name}</h2></div></div>
              <Link href={`/hazard/${tile}/?place=${place.id}`}>Full {TILE_NAME[tile].toLowerCase()} forecast →</Link></div>
            {current && <ForecastStatus tile={current} date={date} />}
            {outlookError ? <p role="status">The neighborhood forecast could not load. <button className="button-link" onClick={() => setOutlookAttempt(x => x + 1)}>Try again</button></p> : !outlook ? <p role="status">Loading neighborhood forecast…</p> :
              forecast ? <p>{date && dayName(date, "long")}: <LevelBadge tile={tile} level={forecast.level} /> {forecast.verdict}</p> :
                <p>{current?.reason ?? "No forecast available for this place and day."}</p>}
            {tile === "water" && !place.coastal ? <p className="notice">Choose a coastal neighborhood to report beach conditions.</p> :
              <ReportBox key={`${place.id}-${tile}`} tile={tile} placeId={place.id} placeName={place.name} />}
          </section>}
          <section className="neighborhood-section" aria-labelledby="neighborhoods-heading">
            <h2 id="neighborhoods-heading">Neighborhoods{onlyGaps && community.data ? " needing observations" : ""}</h2>
            <label className="field-label small" htmlFor="neighborhood-filter">Filter by neighborhood or ZIP</label>
            <input id="neighborhood-filter" type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search San Diego County" />
            <p className="small muted" role="status">{shown.length} neighborhoods</p>
            <ul className="neighborhood-list">{shown.map((p) => {
              const summary = byPlace.get(p.id);
              return <li key={p.id}><button aria-pressed={placeId === p.id} onClick={() => choose(p.id)}>
                <span><strong>{p.name}</strong><span className="small muted">ZIP {p.zip}</span></span>
                <span className="small">{community.data ? COVERAGE_LABEL[coverageFor(summary)] : "Coverage unavailable"}
                  {summary && <span className="muted">{summary.total} observations · {reportAge(summary.last_report_at)}</span>}</span>
              </button></li>;
            })}</ul>
            {shown.length === 0 && <p>No neighborhoods match these filters.</p>}
          </section>
        </div>
      </div>
      <p className="disclaimer">Outlook SD is a forecast, not an official advisory. Follow posted beach signs and official alerts. Only report from a place you are already observing; do not enter a hazardous area to fill a reporting gap.</p>
    </main>
  );
}
