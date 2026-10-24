"use client";
import { Place } from "@/lib/api";
import { useWatchlist } from "@/lib/useWatchlist";

export default function Watchlist({ places, selected, onPick }: { places: Place[]; selected: Place; onPick: (id: string) => void }) {
  const { ids, toggle, notice } = useWatchlist();
  const saved = ids.map(id => places.find(p => p.id === id)).filter((p): p is Place => Boolean(p));
  return <div className="watchlist" aria-label="Saved neighborhoods">
    <div className="watchlist-heading"><span className="eyebrow">Your places</span>
      <button className="button-link" aria-pressed={ids.includes(selected.id)} onClick={() => toggle(selected.id)}>
        {ids.includes(selected.id) ? "★ Saved" : "☆ Save this place"}</button></div>
    {saved.length ? <div className="place-chips">{saved.map(p => <button key={p.id} className="place-chip"
      aria-pressed={p.id === selected.id} onClick={() => onPick(p.id)}>{p.name}</button>)}</div> :
      <p className="small muted">Keep the places you care about one tap away. Saved only on this device.</p>}
    {notice && <p className="small" role="status">{notice}</p>}
  </div>;
}
