import { expect, test } from "@playwright/test";
import { mockCommunityApi } from "./fixtures";

// Network-independent contract fixture, explicitly missing forecasts rather than fabricated live values.
test.beforeEach(async ({ page }) => {
  await mockCommunityApi(page);
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
    let sentHeaders: Record<string, string> | undefined;
    await page.route("**/rest/v1/reports", async (route) => {
      payload = route.request().postDataJSON(); saved = true;
      sentHeaders = route.request().headers();
      await route.fulfill({ status: 201, body: "" });
    });
    await page.route("**/rest/v1/rpc/report_summary", route => route.fulfill({ json: saved ? [{
      place_id: "imperial-beach", hazard: "water", total: 1, reporters: 1,
      problem_reports: 1, clear_reports: 0, last_report_at: new Date().toISOString(), kinds: { water_sewage: 1 },
    }] : [] }));
    await page.goto("/map/?place=imperial-beach");
    await page.getByRole("button", { name: "Sewage smell or brown water", exact: true }).click();
    await expect(page.getByText("Thanks. Your observation for Imperial Beach was saved.")).toBeVisible();
    await expect(page.getByText(/1 observation from 1 browser/)).toBeVisible();
    expect(Object.keys(payload!).sort()).toEqual(["client_id", "hazard", "kind", "place_id", "withdrawal_hash"]);
    expect(payload!.withdrawal_hash).toMatch(/^[0-9a-f]{64}$/);
    expect(payload!.place_id).toBe("imperial-beach");
    expect(payload!.kind).toBe("water_sewage");
    expect(payload!.client_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(sentHeaders!.apikey).toBeTruthy();
    if (sentHeaders!.apikey.startsWith("sb_publishable_")) expect(sentHeaders).not.toHaveProperty("authorization");
    else expect(sentHeaders!.authorization).toBe(`Bearer ${sentHeaders!.apikey}`);
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
    await page.route("**/rest/v1/reports", route => route.fulfill({ status: 400,
      json: { message: "You already sent this report for this place in the last 6 hours" } }));
    await page.goto("/map/?place=imperial-beach");
    await page.getByRole("button", { name: "Sewage smell or brown water", exact: true }).click();
    const reportBox = page.getByRole("region", { name: "What do you see in Imperial Beach?", exact: true });
    await expect(reportBox.getByRole("alert")).toContainText("You already sent this report");
    await expect(page.getByText(/Your observation .* was saved/)).toHaveCount(0);
  });
});

test("saved neighborhoods persist across reload and can be removed", async ({ page }) => {
  await page.goto("/map/?place=imperial-beach");
  await page.getByRole("button", { name: "☆ Save this place", exact: true }).click();
  await expect(page.getByRole("button", { name: "★ Saved", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "★ Saved", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "★ Saved", exact: true }).click();
  await expect(page.getByRole("button", { name: "☆ Save this place", exact: true })).toBeVisible();
});

test("neighborhood and hazard selections follow browser back", async ({ page }) => {
  await page.goto("/map/?place=imperial-beach");
  await expect(page.getByRole("radio", { name: "Water", exact: true })).toBeChecked();
  await page.getByRole("radio", { name: "Heat", exact: true }).check();
  await page.goBack();
  await expect(page.getByRole("radio", { name: "Water", exact: true })).toBeChecked();
  await page.getByRole("radio", { name: "Heat", exact: true }).check();
  await page.getByLabel("Filter by neighborhood or ZIP").fill("91901");
  await page.getByRole("button", { name: /Alpine.*91901/ }).click();
  await expect(page.getByRole("heading", { name: "Alpine", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Imperial Beach", exact: true })).toBeVisible();
});

test("map links restore the selected hazard and forecast date", async ({ page }) => {
  await page.goto("/map/?place=la-jolla&hazard=heat&date=2026-10-26");
  await expect(page.getByRole("radio", { name: "Heat", exact: true })).toBeChecked();
  await expect(page.getByRole("radio", { name: /Mon, Oct 26/ })).toBeChecked();
  await page.getByRole("button", { name: "Share this view" }).click();
  const link = page.getByLabel("Link to this map view");
  await expect(link).toHaveValue(/place=la-jolla&hazard=heat&date=2026-10-26/);
});

test("keyboard navigation can skip directly to the main content", async ({ page, browserName }) => {
  await page.goto("/map/?place=imperial-beach");
  // WebKit on macOS (like Safari's default setting) moves Tab focus only between form controls; Option+Tab reaches links
  await page.keyboard.press(browserName === "webkit" && process.platform === "darwin" ? "Alt+Tab" : "Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();
});
