"use client";
import "maplibre-gl/dist/maplibre-gl.css";
import { layers, namedFlavor } from "@protomaps/basemaps";
import * as maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { useEffect, useMemo, useState } from "react";
import MapGL, { Layer, Marker, NavigationControl, Source } from "react-map-gl/maplibre";
import type { ExpressionSpecification, StyleSpecification } from "maplibre-gl";
import { AQI_HEX, LEVEL_HEX, PMTILES, Place, TileName, get } from "@/lib/api";
import { KINDS, reportCounts, reportsEnabled } from "@/lib/reports";

let protocolAdded = false;
const ASSETS = "https://protomaps.github.io/basemaps-assets";

function baseStyle(): StyleSpecification {
  return {
    version: 8, glyphs: `${ASSETS}/fonts/{fontstack}/{range}.pbf`, sprite: `${ASSETS}/sprites/v4/grayscale`,
    sources: { protomaps: { type: "vector", url: `pmtiles://${PMTILES}`,
      attribution: '<a href="https://protomaps.com">Protomaps</a> © <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>' } },
    layers: layers("protomaps", namedFlavor("grayscale"), { lang: "en" }),
  };
}

const match = (prop: string, table: Record<string, string>, fallback = "#D5DCE3") =>
  ["match", ["coalesce", ["get", prop], "none"], ...Object.entries(table).flat(), fallback] as unknown as ExpressionSpecification;
// CalHeatScore 0–4 → the shared 4-step scale (0 and 1 are both Low)
const CHS_LEVEL = ["match", ["coalesce", ["get", "chs"], -1], 0, LEVEL_HEX.low, 1, LEVEL_HEX.low, 2, LEVEL_HEX.moderate,
  3, LEVEL_HEX.high, 4, LEVEL_HEX.very_high, "#D5DCE3"] as unknown as ExpressionSpecification;

/** Community reports for one hazard, last 7 days, as one point per place (count of problem vs all-clear reports). */
async function reportPoints(tile: TileName): Promise<GeoJSON.FeatureCollection> {
  const [counts, places] = await Promise.all([reportCounts(7), get<Place[]>("places.json")]);
  const problem = new Set(KINDS[tile].filter((k) => k.problem).map((k) => k.kind));
  const by = new Map<string, { p: number; ok: number }>();
  for (const c of counts.filter((c) => c.hazard === tile)) {
    const v = by.get(c.place_id) ?? { p: 0, ok: 0 };
    if (problem.has(c.kind)) v.p += c.n; else v.ok += c.n;
    by.set(c.place_id, v);
  }
  return { type: "FeatureCollection", features: places.filter((p) => by.has(p.id)).map((p) => {
    const v = by.get(p.id)!;
    return { type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat] },
             properties: { name: p.name, problem: v.p, ok: v.ok, total: v.p + v.ok, mostly_problem: v.p >= v.ok } };
  }) };
}

export default function HazardMap({ tile, center, label, showReports = false, marker = true }:
  { tile: TileName; center?: { lat: number; lon: number }; label?: string; showReports?: boolean; marker?: boolean }) {
  const [data, setData] = useState<GeoJSON.FeatureCollection | null>(null);
  const [reports, setReports] = useState<GeoJSON.FeatureCollection | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!protocolAdded && typeof window !== "undefined") {
    maplibregl.addProtocol("pmtiles", new Protocol().tile);
    protocolAdded = true;
  }
  const style = useMemo(baseStyle, []);
  useEffect(() => {
    setData(null); setError(null);
    get<GeoJSON.FeatureCollection>(`map/${tile}.json`).then(setData).catch((e) => setError(String(e.message)));
  }, [tile]);
  useEffect(() => {
    setReports(null);
    if (showReports && reportsEnabled) reportPoints(tile).then(setReports).catch(() => setReports(null));
  }, [tile, showReports]);

  const layer = (() => {
    if (tile === "heat") return <Layer id="hz-heat" type="fill" paint={{ "fill-color": ["case", ["==", ["get", "source"], "outlook"],
      match("level", LEVEL_HEX), CHS_LEVEL] as unknown as ExpressionSpecification, "fill-opacity": 0.45, "fill-outline-color": "#566573" }} />;
    if (tile === "flood") return <Layer id="hz-flood" type="fill" paint={{ "fill-color": match("level", LEVEL_HEX), "fill-opacity": 0.4, "fill-outline-color": "#566573" }} />;
    if (tile === "air") return <Layer id="hz-air" type="circle" paint={{ "circle-radius": 8, "circle-color": match("level", AQI_HEX), "circle-stroke-color": "#16324F", "circle-stroke-width": 1 }} />;
    if (tile === "fire") return [
      <Layer key="cells" id="hz-fire-cells" type="fill" filter={["==", ["geometry-type"], "Polygon"]}
             paint={{ "fill-color": match("level", LEVEL_HEX), "fill-opacity": 0.45 }} />,
      <Layer key="active" id="hz-fire-active" type="circle" filter={["==", ["geometry-type"], "Point"]}
             paint={{ "circle-radius": 8, "circle-color": "#16324F", "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 2 }} />,
    ];
    return <Layer id="hz-water" type="circle" paint={{ "circle-radius": 6, "circle-color": match("level", LEVEL_HEX), "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 1.5 }} />;
  })();

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", minHeight: 320, background: "var(--fog)" }}
         role="region" aria-label={label ?? `Map of ${tile} forecast`}>
      <MapGL mapLib={maplibregl} mapStyle={style} reuseMaps
           initialViewState={{ longitude: center?.lon ?? -117.12, latitude: center?.lat ?? 32.85, zoom: center ? 10.5 : 8.6 }}
           maxBounds={[-118.4, 32.2, -115.4, 33.9]} style={{ position: "absolute", inset: 0 }}>
        <NavigationControl position="top-right" showCompass={false} />
        {data && <Source id="hazard" type="geojson" data={data}>{layer}</Source>}
        {reports && (
          <Source id="reports" type="geojson" data={reports}>
            <Layer id="rp-circle" type="circle" paint={{ "circle-radius": ["interpolate", ["linear"], ["get", "total"], 1, 9, 20, 18],
              "circle-color": ["case", ["get", "mostly_problem"], "#16324F", "#FFFFFF"], "circle-stroke-color": "#16324F", "circle-stroke-width": 2 }} />
            <Layer id="rp-count" type="symbol" layout={{ "text-field": ["to-string", ["get", "total"]], "text-size": 12,
              "text-font": ["Noto Sans Regular"] }} paint={{ "text-color": ["case", ["get", "mostly_problem"], "#FFFFFF", "#16324F"] }} />
          </Source>
        )}
        {center && marker && <Marker longitude={center.lon} latitude={center.lat} color="#005EA2" />}
      </MapGL>
      {error && <p className="small" style={{ position: "absolute", left: 8, bottom: 8, background: "var(--paper)", padding: 6, margin: 0 }}>{error}</p>}
      {data && data.features.length === 0 && (
        <p className="small" style={{ position: "absolute", left: 8, bottom: 8, background: "var(--paper)", padding: 6, margin: 0 }}>
          No map data for this hazard yet.</p>
      )}
    </div>
  );
}
