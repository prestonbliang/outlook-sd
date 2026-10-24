import { expect, test } from "@playwright/test";

// Network-independent contract fixture, explicitly missing forecasts rather than fabricated live values.
test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const places = [
      { id: "imperial-beach", name: "Imperial Beach", zip: "91932", lat: 32.58, lon: -117.12, coastal: true },
      { id: "la-jolla", name: "La Jolla", zip: "92037", lat: 32.85, lon: -117.27, coastal: true },
      { id: "alpine", name: "Alpine", zip: "91901", lat: 32.84, lon: -116.76, coastal: false },
    ];
    let json: unknown = { type: "FeatureCollection", features: [] };
    if (path.endsWith("places.json")) json = places;
    if (path.endsWith("dates.json")) json = { dates: ["2026-10-24", "2026-10-25", "2026-10-26", "2026-10-27"] };
    if (path.includes("/outlook/")) {
      const p = places.find((p) => path.includes(p.id)) ?? places[0];
      json = { place: p, updated_at: null, tiles: ["water", "air", "heat", "flood", "fire"].map((tile) => ({
        tile, days: [], reason: "No forecast available.", factors: [], sources: [], stale_inputs: [],
        official_advisory: { active: null, url: "https://example.com" },
      })) };
    }
    await route.fulfill({ json });
  });
});

test("map can be operated through neighborhood controls without WebGL", async ({ page }) => {
  await page.goto("/map/?place=imperial-beach");
  await expect(page.getByRole("heading", { name: "Explore your neighborhood" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Water", exact: true })).toBeChecked();
  await page.getByRole("radio", { name: "Heat", exact: true }).check();
  await expect(page).toHaveURL(/hazard=heat/);
  await page.getByLabel("Filter by neighborhood or ZIP").fill("91901");
  const alpine = page.getByRole("button", { name: /Alpine.*91901/ });
  await expect(alpine).toBeVisible();
  await alpine.click();
  await expect(page).toHaveURL(/place=alpine/);
  await expect(page.getByRole("heading", { name: "Alpine", exact: true })).toBeVisible();
  await page.getByRole("radio", { name: "Water", exact: true }).check();
  await expect(page.getByText("Choose a coastal neighborhood to report beach conditions.")).toBeVisible();
});

test("mobile map controls do not overflow the page", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/map/?place=imperial-beach");
  await expect(page.getByRole("heading", { name: "Explore your neighborhood" })).toBeVisible();
  await expect(page.getByRole("radio", { name: "Fire", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test.describe("community reporting", () => {
  test.skip(!process.env.E2E_REPORTS_ENABLED, "Build with the fixture Supabase endpoint to exercise report flows");

  test("saving an observation refreshes counts and sends no exact location", async ({ page }) => {
    let saved = false;
    let payload: Record<string, unknown> | undefined;
    await page.route("**/rest/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/reports")) {
        payload = route.request().postDataJSON(); saved = true;
        await route.fulfill({ status: 201, body: "" });
      } else await route.fulfill({ json: saved ? [{
        place_id: "imperial-beach", hazard: "water", total: 1, reporters: 1,
        problem_reports: 1, clear_reports: 0, last_report_at: new Date().toISOString(), kinds: { water_sewage: 1 },
      }] : [] });
    });
    await page.goto("/map/?place=imperial-beach");
    await page.getByRole("button", { name: "Sewage smell or brown water", exact: true }).click();
    await expect(page.getByText("Thanks. Your observation for Imperial Beach was saved.")).toBeVisible();
    await expect(page.getByText(/1 observation from 1 browser/)).toBeVisible();
    expect(Object.keys(payload!).sort()).toEqual(["client_id", "hazard", "kind", "place_id"]);
    expect(payload!.place_id).toBe("imperial-beach");
    expect(payload!.kind).toBe("water_sewage");
    expect(payload!.client_id).toMatch(/^[0-9a-f-]{36}$/);
    await expect(page.getByRole("checkbox", { name: "Highlight reporting blind spots" })).toBeVisible();
  });

  test("a reporting outage is never displayed as zero observations", async ({ page }) => {
    await page.route("**/rest/v1/rpc/report_summary", (route) => route.fulfill({ status: 503, json: {} }));
    await page.goto("/map/?place=imperial-beach");
    await expect(page.getByText("Community observations could not be loaded. Please try again.").first()).toBeVisible();
    await expect(page.getByText(/reporting blind spot for this hazard/)).toHaveCount(0);
    await expect(page.getByRole("checkbox", { name: "Highlight reporting blind spots" })).toHaveCount(0);
  });

  test("repeat-report rejection is explained without claiming success", async ({ page }) => {
    await page.route("**/rest/v1/**", (route) => route.request().url().endsWith("/reports")
      ? route.fulfill({ status: 400, json: { message: "You already sent this report for this place in the last 6 hours" } })
      : route.fulfill({ json: [] }));
    await page.goto("/map/?place=imperial-beach");
    await page.getByRole("button", { name: "Sewage smell or brown water", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("You already sent this report");
    await expect(page.getByText(/Your observation .* was saved/)).toHaveCount(0);
  });
});
