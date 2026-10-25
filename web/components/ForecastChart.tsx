"use client";
import * as Plot from "@observablehq/plot";
import { useEffect, useId, useRef, useState } from "react";
import { Series } from "@/lib/api";

export default function ForecastChart({ series }: { series: Series }) {
  const ref = useRef<HTMLDivElement>(null);
  const [showData, setShowData] = useState(false);
  const [error, setError] = useState(false);
  const [selection, setSelection] = useState(0);
  const inspectorId = useId();
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
        const marks: Plot.Markish[] = [Plot.ruleY([0], { stroke: "#DCE3DF" }),
          Plot.lineY(obs, { x: "t", y: "v", stroke: "#142F35", strokeWidth: 2.25, tip: true,
            title: d => `${series.observed_label ?? "Observed"}\n${d.t.toISOString()}\n${d.v} ${series.units}` }),
          Plot.lineY(fc, { x: "t", y: "v", stroke: "#086A70", strokeWidth: 2.25, strokeDasharray: "4,4", tip: true,
            title: d => `Forecast\n${d.t.toISOString()}\n${d.v} ${series.units}` })];
        if (fc.some(d => d.hi !== undefined)) marks.push(Plot.lineY(fc, { x: "t", y: "hi", stroke: "#086A70", strokeDasharray: "1,4", strokeOpacity: .6 }));
        if (series.threshold) {
          marks.push(Plot.ruleY([series.threshold.value], { stroke: "#8B1A3A", strokeOpacity: .8 }));
          marks.push(Plot.text([series.threshold], { y: "value", text: "label", frameAnchor: "left", dy: -7, fill: "#8B1A3A", fontSize: 12 }));
        }
        chart?.remove();
        chart = Plot.plot({ width, height: 280, marginLeft: 54, style: { fontFamily: "Public Sans, system-ui", fontSize: "11px", background: "transparent" },
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
  const selected = points[Math.min(selection, points.length - 1)];
  const selectedText = selected ? `${selected.type} · ${selected.t} · ${selected.v} ${series.units}${selected.hi !== undefined ? ` · High end ${selected.hi} ${series.units}` : ""}` : "";
  return <figure className="forecast-chart">
    <div className="chart-legend" aria-hidden="true"><span><i />{series.observed_label ?? "Observed"}</span><span><i className="forecast-key" />Forecast</span></div>
    <div ref={ref} role="img" aria-label={`Chart in ${series.units}. ${series.observed.length} historical points and ${series.forecast.length} forecast points. Exact values are available in the data table.`} />
    {error && <p role="status">The chart could not be drawn. Exact values are available below.</p>}
    <figcaption className="small muted">Solid: {series.observed_label ?? "observed"}. Teal dashed line: forecast. {series.forecast.some(d => d.hi !== undefined) && "Fainter dotted line: high end."} Times on the chart are UTC.</figcaption>
    {selected && <div className="chart-inspector"><label htmlFor={inspectorId}>Inspect chart point</label>
      <input id={inspectorId} type="range" min={0} max={points.length - 1} step={1} value={Math.min(selection, points.length - 1)}
        disabled={points.length < 2} aria-valuetext={selectedText} onChange={event => setSelection(Number(event.target.value))} />
      <output htmlFor={inspectorId} aria-live="polite">{selectedText}</output></div>}
    <details onToggle={event => setShowData(event.currentTarget.open)}><summary>View chart data ({points.length} points)</summary>
      {showData && <div className="table-scroll"><table><caption>{series.units} · timestamps as supplied by the source</caption>
        <thead><tr><th scope="col">Time</th><th scope="col">Type</th><th scope="col">Value</th><th scope="col">High end</th></tr></thead>
        <tbody>{points.map((d, index) => <tr key={`${d.type}-${d.t}-${index}`}><th scope="row">{d.t}</th><td>{d.type}</td><td>{d.v}</td><td>{d.hi ?? "—"}</td></tr>)}</tbody>
      </table>{!points.length && <p>No chart data available.</p>}</div>}
    </details>
  </figure>;
}
