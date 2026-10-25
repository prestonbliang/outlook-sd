"use client";
import dynamic from "next/dynamic";
import { useId, useState } from "react";
import { Place } from "@/lib/api";
import { useWatchlist } from "@/lib/useWatchlist";
const SavedPlaceComparison = dynamic(() => import("./SavedPlaceComparison"), {
  loading: () => <p className="small" role="status">Loading saved-place comparison…</p>,
});

export default function Watchlist({ places, selected, onPick }: { places: Place[]; selected: Place; onPick: (id: string) => void }) {
  const { ids, toggle, notice } = useWatchlist();
  const [comparing, setComparing] = useState(false);
  const panelId = useId();
  const saved = ids.map(id => places.find(p => p.id === id)).filter((p): p is Place => Boolean(p));
  return <div className="watchlist" aria-label="Saved neighborhoods">
    <div className="watchlist-heading"><span className="eyebrow">Your places</span>
      <button className="button-link" aria-pressed={ids.includes(selected.id)} onClick={() => toggle(selected.id)}>
        {ids.includes(selected.id) ? "★ Saved" : "☆ Save this place"}</button></div>
    {saved.length ? <div className="place-chips">{saved.map(p => <button key={p.id} className="place-chip"
      aria-pressed={p.id === selected.id} onClick={() => onPick(p.id)}>{p.name}</button>)}</div> : null}
    {notice && <p className="small" role="status">{notice}</p>}
    {saved.length > 0 && <button className="button-link comparison-toggle" aria-expanded={comparing}
      aria-controls={panelId} onClick={() => setComparing(value => !value)}>{comparing ? "Close comparison" : "Compare saved places"}</button>}
    {comparing && saved.length > 0 && <div id={panelId}><SavedPlaceComparison places={saved} onPick={onPick} /></div>}
  </div>;
}
