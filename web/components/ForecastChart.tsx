"use client";
import * as Plot from "@observablehq/plot";
import { useEffect, useRef } from "react";
import { Series } from "@/lib/api";

/** Past 7 days observed (solid), next days forecast (dotted), threshold as a labeled rule. One color. */
export default function ForecastChart({ series }: { series: Series }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const parse = (t: string) => new Date(t.length === 10 ? `${t}T12:00:00` : t);
    const obs = series.observed.map((d) => ({ t: parse(d.t), v: d.v }));
    const fc = series.forecast.map((d) => ({ t: parse(d.t), v: d.v, hi: d.hi }));
    const ink = "#16324F";
    const marks: Plot.Markish[] = [
      Plot.ruleY([0], { stroke: "#D5DCE3" }),
      Plot.lineY(obs, { x: "t", y: "v", stroke: ink, strokeWidth: 2 }),
      Plot.lineY(fc, { x: "t", y: "v", stroke: ink, strokeWidth: 2, strokeDasharray: "2,4" }),
    ];
    if (fc.some((d) => d.hi !== undefined)) marks.push(Plot.lineY(fc, { x: "t", y: "hi", stroke: ink, strokeWidth: 1, strokeDasharray: "1,3", strokeOpacity: 0.6 }));
    if (series.threshold) {
      marks.push(Plot.ruleY([series.threshold.value], { stroke: ink, strokeOpacity: 0.7 }));
      marks.push(Plot.text([series.threshold], { y: "value", text: "label", frameAnchor: "left", dy: -7, fill: ink, fontSize: 12 }));
    }
    const chart = Plot.plot({
      width: el.clientWidth || 600, height: 220, marginLeft: 44, style: { fontFamily: "Public Sans, system-ui", fontSize: "12px", color: ink },
      x: { type: "time", label: null }, y: { label: series.units, grid: false }, marks,
    });
    el.replaceChildren(chart);
    return () => chart.remove();
  }, [series]);
  const n = series.observed.length + series.forecast.length;
  return (
    <figure style={{ margin: "8px 0" }}>
      <div ref={ref} role="img" aria-label={`Chart: ${series.units}. ${series.observed.length} observed points (solid line), ${series.forecast.length} forecast points (dotted line).`} />
      <figcaption className="small muted">
        Solid: {series.observed_label ?? "observed"}. Dotted: forecast{series.forecast.some((d) => d.hi !== undefined) ? " (fainter dots: high end)" : ""}.
        {n === 0 && " No data yet."}
      </figcaption>
    </figure>
  );
}
