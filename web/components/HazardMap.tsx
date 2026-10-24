"use client";
import "maplibre-gl/dist/maplibre-gl.css";
import Link from "next/link";
import { layers, namedFlavor } from "@protomaps/basemaps";
import * as maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { useEffect, useMemo, useRef, useState } from "react";
import MapGL, { Layer, Marker, NavigationControl, Popup, ScaleControl, Source } from "react-map-gl/maplibre";
import type { MapRef, MapLayerMouseEvent } from "react-map-gl/maplibre";
import type { ExpressionSpecification, StyleSpecification } from "maplibre-gl";
import { AQI_HEX, LEVEL_HEX, LEVEL_WORD, PMTILES, Place, TILE_NAME, TileName, get, haversineKm, updatedText } from "@/lib/api";
import { COVERAGE_LABEL, coverageFor, reportAge, type Summary } from "@/lib/community";

let protocolAdded = false;
const ASSETS = "/map-assets";
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

export type MapData = GeoJSON.FeatureCollection & { date?: string; mode?: string; run_ts?: string; stale_inputs?: string[]; context_notice?: string | null };
type Selection = { lon: number; lat: number; properties: Record<string, unknown>; place?: Place };

export default function HazardMap({ tile, date, center, label, places = [], summaries = null, showReports = false,
  showCoverage = false, marker = true, observationsOnPage = false, onPlacePick }: {
  tile: TileName; date?: string; center?: { lat: number; lon: number }; label?: string;
  places?: Place[]; summaries?: Summary[] | null; showReports?: boolean; showCoverage?: boolean;
  marker?: boolean; observationsOnPage?: boolean; onPlacePick?: (place: Place) => void;
}) {
  const mapRef = useRef<MapRef>(null);
  const [data, setData] = useState<MapData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mapError, setMapError] = useState(false);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [hover, setHover] = useState(false);
  const [ready, setReady] = useState(false);
  if (!protocolAdded && typeof window !== "undefined") {
    maplibregl.setWorkerUrl("/map-assets/maplibre-gl-worker.mjs");
    maplibregl.addProtocol("pmtiles", new Protocol().tile);
    protocolAdded = true;
  }
  const style = useMemo(baseStyle, []);
  useEffect(() => {
    const controller = new AbortController();
    setData(null); setError(null); setSelection(null);
    get<MapData>(`map/${tile}${date ? `-${date}` : ""}.json`, controller.signal)
      .then(setData).catch((e) => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [tile, date]);
  useEffect(() => {
    if (ready && center) mapRef.current?.easeTo({ center: [center.lon, center.lat], zoom: 10.5,
      duration: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 500 });
  }, [center?.lat, center?.lon, ready]);

  const summaryByPlace = useMemo(() => new Map(summaries?.filter(s => s.hazard === tile).map(s => [s.place_id, s])), [summaries, tile]);
  const neighborhoodData = useMemo<GeoJSON.FeatureCollection>(() => ({
    type: "FeatureCollection", features: places.filter((p) => tile !== "water" || p.coastal).map((p) => {
      const summary = summaryByPlace.get(p.id);
      return { type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat] },
        properties: { id: p.id, name: p.name, neighborhood: true, coverage: coverageFor(summary),
          total: summary?.total ?? 0, problem: summary?.problem_reports ?? 0, clear: summary?.clear_reports ?? 0 } };
    }),
  }), [places, summaryByPlace, tile]);
  const interactive = [
    ...(data ? tile === "fire" ? ["hz-fire-cells", "hz-fire-active"] : [`hz-${tile}`] : []),
    ...(places.length ? ["neighborhoods"] : []),
    ...(summaries !== null && showReports ? ["rp-circle"] : []),
    ...(summaries !== null && showCoverage ? ["coverage-circle"] : []),
  ];
  function inspect(event: MapLayerMouseEvent) {
    const feature = event.features?.[0];
    if (!feature) { setSelection(null); return; }
    const p = feature.properties ?? {};
    const point = { lon: event.lngLat.lng, lat: event.lngLat.lat };
    const selectedPlace = places.find((x) => x.id === p.id);
    const candidates = tile === "water" ? places.filter(place => place.coastal) : places;
    const nearest = selectedPlace ?? candidates.reduce<Place | undefined>((best, place) =>
      !best || haversineKm(point, place) < haversineKm(point, best) ? place : best, undefined);
    const nearby = nearest && haversineKm(point, nearest) <= 30 ? nearest : undefined;
    setSelection({ ...point, properties: p, place: nearby });
    if (nearby) onPlacePick?.(nearby);
  }
  const selectedSummary = selection?.place ? summaryByPlace.get(selection.place.id) : undefined;
  const p = selection?.properties;
  const hazardLayers = (() => {
    if (tile === "heat" || tile === "flood") return <Layer id={`hz-${tile}`} type="fill"
      paint={{ "fill-color": match("level", LEVEL_HEX), "fill-opacity": 0.45, "fill-outline-color": "#566573" }} />;
    if (tile === "air") return <Layer id="hz-air" type="circle" paint={{ "circle-radius": 9,
      "circle-color": match("level", AQI_HEX), "circle-stroke-color": "#16324F", "circle-stroke-width": 2 }} />;
    if (tile === "fire") return [
      <Layer key="cells" id="hz-fire-cells" type="fill" filter={["==", ["geometry-type"], "Polygon"]}
        paint={{ "fill-color": match("level", LEVEL_HEX), "fill-opacity": ["case", ["==", ["get", "level"], "low"], 0.12, 0.45] }} />,
      <Layer key="active" id="hz-fire-active" type="circle" filter={["==", ["geometry-type"], "Point"]}
        paint={{ "circle-radius": 9, "circle-color": "#16324F", "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 2 }} />,
    ];
    return <Layer id="hz-water" type="circle" paint={{ "circle-radius": 8, "circle-color": match("level", LEVEL_HEX),
      "circle-stroke-color": "#FFFFFF", "circle-stroke-width": 2 }} />;
  })();
  return (
    <div className="hazard-map" role="region" aria-busy={!ready} aria-label={label ?? `San Diego ${TILE_NAME[tile].toLowerCase()} map`}>
      <MapGL ref={mapRef} mapLib={maplibregl} mapStyle={style} reuseMaps
        initialViewState={{ longitude: center?.lon ?? -116.9, latitude: center?.lat ?? 33, zoom: center ? 10.5 : 8.5 }}
        maxBounds={[-118.4, 32.2, -115.4, 33.9]} minZoom={7} style={{ position: "absolute", inset: 0 }}
        interactiveLayerIds={interactive} onClick={inspect} cursor={hover ? "pointer" : "grab"}
        onMouseMove={(e) => setHover(Boolean(e.features?.length))} onMouseLeave={() => setHover(false)}
        onLoad={() => { setReady(true); setMapError(false); }} onError={() => setMapError(true)}>
        <NavigationControl position="top-right" showCompass={false} />
        <ScaleControl position="bottom-right" unit="imperial" />
        {data && <Source key={`${tile}-${date}`} id="hazard" type="geojson" data={data}>{hazardLayers}</Source>}
        {places.length > 0 && <Source id="neighborhoods" type="geojson" data={neighborhoodData}>
          <Layer id="neighborhoods" type="circle" paint={{ "circle-radius": 4, "circle-color": "#FFFFFF",
            "circle-stroke-color": "#566573", "circle-stroke-width": 1 }} />
          {summaries !== null && showCoverage && <Layer id="coverage-circle" type="circle"
            filter={["!=", ["get", "coverage"], "reported"]} paint={{ "circle-radius": 12, "circle-color": "#6A4C93",
              "circle-opacity": 0.12, "circle-stroke-color": "#6A4C93", "circle-stroke-width": 2 }} />}
          {summaries !== null && showReports && <Layer id="rp-circle" type="circle"
            filter={[">", ["get", "total"], 0]} paint={{ "circle-radius": ["interpolate", ["linear"], ["get", "total"], 1, 8, 20, 18],
              "circle-color": ["case", [">", ["get", "problem"], ["get", "clear"]], "#16324F", "#FFFFFF"],
              "circle-stroke-color": "#16324F", "circle-stroke-width": 2 }} />}
        </Source>}
        {center && marker && <Marker longitude={center.lon} latitude={center.lat} color="#005EA2" />}
        {selection && <Popup longitude={selection.lon} latitude={selection.lat} closeOnClick={false}
          onClose={() => setSelection(null)} maxWidth="300px" className="hazard-popup">
          <p className="eyebrow">{TILE_NAME[tile]} · {data?.mode === "observation" ? "Observed" : date ?? data?.date ?? "Today"}</p>
          <h3>{String(p?.name ?? (p?.zip ? `ZIP ${p.zip}` : p?.cell ? `Area ${p.cell}` : "Selected area"))}</h3>
          {typeof p?.level === "string" && <p><strong>{LEVEL_WORD[p.level] ?? p.level}</strong>{p.label ? ` · ${p.label}` : ""}</p>}
          {tile === "water" && typeof p?.value === "number" && <p>{Math.round(p.value * 100)}% predicted chance above the bacteria standard.</p>}
          {typeof p?.aqi === "number" && <p>AQI {Math.round(p.aqi)} · {String(p.parameter)}</p>}
          {typeof p?.peak_ft_mllw === "number" && <p>Bay peak: {p.peak_ft_mllw.toFixed(1)} ft above MLLW. Approximate shoreline coverage.</p>}
          {p?.active_fire === true && <p>Last reported incident · {String(p.acres ?? "Unknown")} acres · {String(p.contained_pct ?? "Unknown")}% contained.</p>}
          {typeof p?.chs === "number" && <p>State CalHeatScore: {p.chs} of 4.</p>}
          {selection.place && <>
            <p className="small muted">Neighborhood: {selection.place.name}</p>
            {summaries !== null && <p className="small">{COVERAGE_LABEL[coverageFor(selectedSummary)]}
              {selectedSummary && ` · ${selectedSummary.total} observations · ${reportAge(selectedSummary.last_report_at)}`}</p>}
            {onPlacePick && (observationsOnPage ? <button className="button-link" onClick={() => {
              onPlacePick?.(selection.place!);
              document.getElementById("map-report")?.scrollIntoView({ behavior: "auto", block: "start" });
              document.getElementById("map-report")?.focus({ preventScroll: true });
            }}>View neighborhood observations</button> : <p><Link href={`/map/?place=${selection.place.id}&hazard=${tile}#map-report`}>View neighborhood observations</Link></p>)}
            <p><Link href={`/hazard/${tile}/?place=${selection.place.id}`}>Forecast and official source →</Link></p>
          </>}
        </Popup>}
      </MapGL>
      <button className="map-reset" onClick={() => {
        mapRef.current?.fitBounds([[-117.65, 32.53], [-116.08, 33.51]], { padding: 35, duration: 0 });
      }}>Show county</button>
      <div className="map-status small" role="status">
        {error ? "Forecast layer could not load. Try another hazard or reload." : !data ? "Loading forecast layer…" :
          !data.features.some((f) => f.properties?.level || f.properties?.active_fire) ? "No map forecast data available for this day." :
          `${data.mode === "observation" ? "Current observations" : "Forecast"} · ${updatedText(data.run_ts ?? null)}`}
        {data?.stale_inputs?.length ? " · Some source data is not current." : ""}
        {data?.context_notice && <span> {data.context_notice}</span>}
        {mapError && <span> Background map or map assets could not load. Use the neighborhood list below.</span>}
      </div>
    </div>
  );
}
