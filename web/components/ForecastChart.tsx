"use client";
import * as Plot from "@observablehq/plot";
import { useEffect, useRef, useState } from "react";
import { Series } from "@/lib/api";

export default function ForecastChart({ series }: { series: Series }) {
  const ref = useRef<HTMLDivElement>(null);
  const [showData, setShowData] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let chart: ReturnType<typeof Plot.plot> | undefined;
    let frame = 0;
    let previousWidth = 0;
    const parse = (time: string) => new Date(time.length === 10 ? `${time}T12:00:00Z` : time);
    function draw() {
      const width = Math.round(el!.clientWidth) || 600;
      if (width === previousWidth) return;
      previousWidth = width;
      try {
        const obs = series.observed.map(d => ({ t: parse(d.t), v: d.v }));
        const fc = series.forecast.map(d => ({ t: parse(d.t), v: d.v, hi: d.hi }));
        const marks: Plot.Markish[] = [Plot.ruleY([0], { stroke: "#D5DCE3" }),
          Plot.lineY(obs, { x: "t", y: "v", stroke: "#16324F", strokeWidth: 2 }),
          Plot.lineY(fc, { x: "t", y: "v", stroke: "#007F82", strokeWidth: 2, strokeDasharray: "3,4" })];
        if (fc.some(d => d.hi !== undefined)) marks.push(Plot.lineY(fc, { x: "t", y: "hi", stroke: "#007F82", strokeDasharray: "1,3", strokeOpacity: .6 }));
        if (series.threshold) {
          marks.push(Plot.ruleY([series.threshold.value], { stroke: "#8B1A3A", strokeOpacity: .8 }));
          marks.push(Plot.text([series.threshold], { y: "value", text: "label", frameAnchor: "left", dy: -7, fill: "#8B1A3A", fontSize: 12 }));
        }
        chart?.remove();
        chart = Plot.plot({ width, height: 240, marginLeft: 54, style: { fontFamily: "Public Sans, system-ui", fontSize: "12px" },
          x: { type: "utc", label: "Time (UTC)" }, y: { label: series.units, grid: true }, marks });
        // The labelled image wrapper and exact-values table are the accessible alternatives.
        chart.setAttribute("aria-hidden", "true");
        el!.replaceChildren(chart); setError(false);
      } catch { setError(true); }
    }
    draw();
    const observer = new ResizeObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(draw); });
    observer.observe(el);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); chart?.remove(); };
  }, [series]);
  const points = [...series.observed.map(d => ({ ...d, hi: undefined as number | undefined, type: series.observed_label ?? "Observed" })),
    ...series.forecast.map(d => ({ ...d, type: "Forecast" }))];
  return <figure className="forecast-chart">
    <div ref={ref} role="img" aria-label={`Chart in ${series.units}. ${series.observed.length} historical points and ${series.forecast.length} forecast points. Exact values are available in the data table.`} />
    {error && <p role="status">The chart could not be drawn. Exact values are available below.</p>}
    <figcaption className="small muted">Solid: {series.observed_label ?? "observed"}. Teal dashed line: forecast. {series.forecast.some(d => d.hi !== undefined) && "Fainter dotted line: high end."} Times on the chart are UTC.</figcaption>
    <details onToggle={event => setShowData(event.currentTarget.open)}><summary>View chart data ({points.length} points)</summary>
      {showData && <div className="table-scroll"><table><caption>{series.units} · timestamps as supplied by the source</caption>
        <thead><tr><th scope="col">Time</th><th scope="col">Type</th><th scope="col">Value</th><th scope="col">High end</th></tr></thead>
        <tbody>{points.map((d, index) => <tr key={`${d.type}-${d.t}-${index}`}><th scope="row">{d.t}</th><td>{d.type}</td><td>{d.v}</td><td>{d.hi ?? "—"}</td></tr>)}</tbody>
      </table>{!points.length && <p>No chart data available.</p>}</div>}
    </details>
  </figure>;
}
