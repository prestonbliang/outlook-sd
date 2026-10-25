import type { Page } from "@playwright/test";

// Deliberately synthetic, browser-test-only records. Never imported by application code.
export const QA_NOW = "2026-10-24T18:00:00Z";
export const QA_PLACES = [
  { id: "imperial-beach", name: "Imperial Beach", zip: "91932", lat: 32.58, lon: -117.12, coastal: true, kind: "place" },
  { id: "la-jolla", name: "La Jolla", zip: "92037", lat: 32.85, lon: -117.27, coastal: true, kind: "place" },
  { id: "alpine", name: "Alpine", zip: "91901", lat: 32.84, lon: -116.76, coastal: false, kind: "place" },
];
export const QA_TILES = ["water", "air", "heat", "flood", "fire"];
export function emptyTile(tile: string) {
  return { tile, days: [], verdict: `${tile[0].toUpperCase()}${tile.slice(1)} forecast unavailable`,
    reason: "No forecast available.", factors: [], sources: ["Browser test fixture"], stale_inputs: [],
    official_advisory: { active: null, url: "https://www.weather.gov/sgx/" } };
}
export function heatFixture() {
  return { ...emptyTile("heat"), model: "outlook", run_ts: QA_NOW, verdict: undefined,
    days: [{ date: "2026-10-24", value: 1.2, level: "moderate", verdict: "Moderate heat risk", expected_calls: 12, normal_calls: 10, high_f: 85 },
      { date: "2026-10-25", value: 0, level: "low", verdict: "Low", expected_calls: 10, normal_calls: 10, high_f: 78 }],
    place: QA_PLACES[0], window: { verdict: "Moderate heat risk", through: "2026-10-24" },
    what_to_do: "Browser test fixture advice.", metrics: null,
    series: { units: "°F", threshold: null, observed_label: "Test history",
      observed: [{ t: "2026-10-23", v: 79 }], forecast: [{ t: "2026-10-24", v: 85, hi: 90 }] } };
}
export async function mockApi(page: Page) {
  await page.clock.setFixedTime(new Date(QA_NOW));
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const place = QA_PLACES.find(p => path.includes(p.id)) ?? QA_PLACES[0];
    let json: unknown = { type: "FeatureCollection", features: [], date: "2026-10-24", stale_inputs: [] };
    if (path.endsWith("places.json")) json = QA_PLACES;
    else if (path.endsWith("build.json")) json = { schema_version: 1, generated_at: QA_NOW, forecast_date: "2026-10-24", source_commit: "123456789abcdef" };
    else if (path.endsWith("dates.json")) json = { dates: ["2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27"] };
    else if (path.includes("/outlook/")) json = { place, updated_at: null, tiles: QA_TILES.map(emptyTile) };
    else if (path.includes("/hazard/")) {
      const tile = path.split("/").at(-2)!;
      json = { ...emptyTile(tile), place, window: null, series: null, what_to_do: "No model forecast. Check the official source.", metrics: null };
    } else if (path.endsWith("health.json")) json = { sources: {} };
    else if (path.endsWith("scenarios.json")) json = {
      flow: { period: "2017-01-01 → 2021-05-26", samples: 100, no_cap_unsafe_share: 0.2, recent_mgd: 40,
        caps: [0, 5, 10, 15, 20, 25].map(c => ({ cap_mgd: c, unsafe_share: c / 200 })) },
      sea_level: { period: "2014–2025", minor_flood_ft_mllw: 7.59, rises: [0, 0.25, 0.5, 0.75, 1].map(r => ({ rise_ft: r, days_per_year: 5 + r * 80 })) } };
    else if (path.endsWith("track-record.json")) json = { tiles: Object.fromEntries(QA_TILES.map(t => [t, { held_out: null, live: null, community: null }])) };
    await route.fulfill({ json });
  });
  await page.route("**/rest/v1/rpc/report_summary", route => route.fulfill({ json: [] }));
}
