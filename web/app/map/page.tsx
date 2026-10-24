"use client";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";
import { AQI_HEX, LEVEL_HEX, LEVEL_WORD, TILE_NAME, TILE_ORDER, TileName } from "@/lib/api";
import { reportsEnabled } from "@/lib/reports";
import { usePlace } from "@/lib/usePlace";

const HazardMap = dynamic(() => import("@/components/HazardMap"), { ssr: false });
const NOTES: Record<TileName, string> = {
  water: "Monitored beach stations, today's chance of bacteria above the state standard.",
  air: "AirNow monitors, current AQI. Forecast coming soon.",
  heat: "ZIP codes: Outlook SD heat model in City of San Diego Fire-Rescue ZIPs, the state CalHeatScore elsewhere.",
  flood: "Places along the ocean and bay shore, colored by today's forecast peak at the San Diego Bay gauge. Approximate.",
  fire: "2 km areas rated Moderate or higher for a new large fire today (Low areas are not shaded). Dark dots: active CAL FIRE incidents.",
};

export default function MapPage() {
  const { place, placeId } = usePlace();
  const [tile, setTile] = useState<TileName>("water");
  const [showReports, setShowReports] = useState(true);
  const legend = tile === "air" ? AQI_HEX : LEVEL_HEX;
  return (
    <main className="wrap" style={{ maxWidth: 1100 }}>
      <p className="small"><Link href={`/?place=${placeId ?? ""}`}>← Today</Link></p>
      <h1>Map</h1>
      <fieldset style={{ border: 0, padding: 0, margin: "12px 0", display: "flex", gap: 16, flexWrap: "wrap" }}>
        <legend className="small" style={{ fontWeight: 600, marginBottom: 4 }}>Hazard</legend>
        {TILE_ORDER.map((t) => (
          <label key={t} style={{ display: "flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
            <input type="radio" name="hazard" checked={tile === t} onChange={() => setTile(t)} />{TILE_NAME[t]}
          </label>
        ))}
      </fieldset>
      <p className="small muted" style={{ margin: "0 0 8px" }}>{NOTES[tile]}</p>
      {reportsEnabled && (
        <label className="small" style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 8 }}>
          <input type="checkbox" checked={showReports} onChange={(e) => setShowReports(e.target.checked)} />
          Show community reports, last 7 days (number = reports; dark circle = mostly problem reports, white = mostly all-clear)
        </label>
      )}
      <div style={{ height: "60vh", minHeight: 360, border: "1px solid var(--rule)" }}>
        <HazardMap tile={tile} center={place ?? undefined} showReports={showReports} marker={false} />
      </div>
      <ul aria-label="Legend" style={{ listStyle: "none", padding: 0, display: "flex", gap: 16, flexWrap: "wrap", margin: "10px 0" }}>
        {Object.entries(legend).map(([k, hex]) => (
          <li key={k} style={{ display: "flex", gap: 6, alignItems: "center" }} className="small">
            <span aria-hidden style={{ width: 14, height: 14, background: hex, border: "1px solid var(--rule)" }} />{LEVEL_WORD[k]}
          </li>
        ))}
        <li className="small" style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span aria-hidden style={{ width: 14, height: 14, background: "#D5DCE3" }} />No rating
        </li>
      </ul>
    </main>
  );
}
