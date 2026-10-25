"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { LEVEL_WORD, TILE_NAME, TILE_ORDER, get, type Outlook, type Place } from "@/lib/api";
import { currentDay, forecastState } from "@/lib/forecast";
import { useNow } from "@/lib/useNow";

type Result = { outlook?: Outlook; error?: string };
export default function SavedPlaceComparison({ places, onPick }: { places: Place[]; onPick: (id: string) => void }) {
  const now = useNow();
  const [results, setResults] = useState<Record<string, Result>>({});
  const [attempt, setAttempt] = useState(0);
  const ids = places.map(p => p.id).join(",");
  useEffect(() => {
    const controller = new AbortController();
    setResults({});
    for (const id of ids.split(",").filter(Boolean)) {
      get<Outlook>(`outlook/${id}.json`, controller.signal).then(outlook => {
        if (outlook.place?.id !== id || !Array.isArray(outlook.tiles)) throw new Error("The neighborhood forecast could not be read.");
        if (!controller.signal.aborted) setResults(previous => ({ ...previous, [id]: { outlook } }));
      }).catch(error => {
        if (!controller.signal.aborted) setResults(previous => ({ ...previous, [id]: { error: error.message } }));
      });
    }
    return () => controller.abort();
  }, [ids, attempt]);
  return <div className="saved-comparison">
    <p className="small muted">Today across your saved neighborhoods. Older and missing forecasts stay marked as unknown.</p>
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Saved neighborhood forecast comparison">
      <table><caption>Today’s ratings · scroll horizontally to compare all five hazards</caption>
        <thead><tr><th scope="col">Neighborhood</th>{TILE_ORDER.map(t => <th scope="col" key={t}>{TILE_NAME[t]}</th>)}</tr></thead>
        <tbody>{places.map(place => {
          const result = results[place.id];
          return <tr key={place.id}><th scope="row"><button className="button-link" onClick={() => onPick(place.id)}>{place.name}</button></th>
            {!result ? <td colSpan={5}>Loading {place.name}…</td> : result.error ? <td colSpan={5}>{result.error}</td> : TILE_ORDER.map(hazard => {
              const tile = result.outlook?.tiles.find(t => t.tile === hazard);
              const state = tile ? forecastState(tile, now) : "unavailable";
              const day = tile ? currentDay(tile, new Date(now)) : undefined;
              return <td key={hazard}><Link className={`comparison-rating state-${state}`} href={`/hazard/${hazard}/?place=${place.id}`}>
                {state === "current" ? LEVEL_WORD[day?.level ?? ""] ?? "Not rated" : state === "stale" ? "Needs updating" :
                  state === "not_applicable" ? "Outside coverage" : "No forecast"}</Link></td>;
            })}</tr>;
        })}</tbody>
      </table>
    </div>
    <button className="button-link" onClick={() => setAttempt(x => x + 1)}>Refresh saved forecasts</button>
  </div>;
}
