import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { emptyTile, heatFixture, mockApi, QA_PLACES, QA_TILES } from "./fixtures";

test.beforeEach(async ({ page }) => { await mockApi(page); });

test("first-time navigation keeps the neighborhood across every page", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Imperial Beach", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Change place", exact: true }).click();
  await page.getByLabel("Neighborhood or ZIP", { exact: true }).fill("La Jolla");
  await page.getByRole("button", { name: "La Jolla · 92037", exact: true }).click();
  await expect(page.getByRole("button", { name: "Change place", exact: true })).toBeFocused();
  const nav = page.getByRole("navigation", { name: "Primary navigation" });
  for (const [name, heading] of [["Map & reports", "Explore your neighborhood"], ["Track record", "Track record"], ["Our data", "Data"], ["Today", "La Jolla"]]) {
    await nav.getByRole("link", { name, exact: true }).click();
    await expect(page).toHaveURL(/place=la-jolla/);
    await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    await expect(nav.getByRole("link", { name, exact: true })).toHaveAttribute("aria-current", "page");
  }
  expect(errors).toEqual([]);
});

test("back restores the initial place even when the first URL has no query", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Change place", exact: true }).click();
  await page.getByLabel("Neighborhood or ZIP", { exact: true }).fill("Alpine");
  await page.getByRole("button", { name: "Alpine · 91901", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Alpine", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Imperial Beach", exact: true })).toBeVisible();
});

test("the map renders from local assets or explains unavailable WebGL", async ({ page }) => {
  const workers: string[] = [];
  page.on("worker", worker => workers.push(worker.url()));
  // The basemap, fonts, sprites and module worker must not depend on third-party requests.
  await page.route(/^https?:\/\/(?!127\.0\.0\.1:4399\/).*/, route => route.abort());
  await page.goto("/map/?place=imperial-beach");
  const webgl = await page.evaluate(() => Boolean(document.createElement("canvas").getContext("webgl2")));
  if (webgl) {
    await expect(page.getByRole("region", { name: "San Diego water map", exact: true })).toHaveAttribute("aria-busy", "false", { timeout: 20000 });
    expect(workers.some(url => url.includes("/map-assets/maplibre-gl-worker.mjs"))).toBe(true);
    expect(workers.every(url => !url.includes("/map/?"))).toBe(true);
  } else {
    await expect(page.getByRole("heading", { name: "Map view unavailable" })).toBeVisible();
  }
});

test("forecast failures recover through the retry control", async ({ page }) => {
  let available = false;
  await page.route("**/api/outlook/*.json", route => available
    ? route.fulfill({ json: { place: QA_PLACES[0], updated_at: null, tiles: QA_TILES.map(emptyTile) } })
    : route.fulfill({ status: 503, json: {} }));
  await page.goto("/?place=imperial-beach");
  await expect(page.getByRole("alert").filter({ hasText: "Your outlook could not load" })).toBeVisible();
  available = true;
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.locator("main .hazard-card")).toHaveCount(5);
  await expect(page.getByText("No forecasts are available for today.", { exact: false })).toBeVisible();
});

test("denied geolocation offers an immediate search alternative", async ({ page }) => {
  await page.addInitScript(() => {
    navigator.geolocation.getCurrentPosition = (_success, error) => error?.({ code: 1, message: "Denied" } as GeolocationPositionError);
  });
  await page.goto("/map/?place=imperial-beach");
  await page.getByRole("button", { name: "Use my location", exact: true }).click();
  await expect(page.getByText("Location permission was not given. Pick a place instead.")).toBeVisible();
  await page.getByLabel("Neighborhood or ZIP", { exact: true }).fill("91901");
  await page.getByLabel("Neighborhood or ZIP", { exact: true }).press("Enter");
  await expect(page.getByRole("heading", { name: "Alpine", exact: true })).toBeVisible();
});

test("saved-place storage failures are explained without breaking selection", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", { value: {
      getItem() { throw new DOMException("Blocked", "SecurityError"); },
      setItem() { throw new DOMException("Blocked", "SecurityError"); },
    } });
  });
  await page.goto("/map/?place=imperial-beach");
  await page.getByRole("button", { name: "☆ Save this place", exact: true }).click();
  await expect(page.getByText("Saved for this visit. Enable site storage to keep these places for next time.")).toBeVisible();
  await expect(page.getByRole("button", { name: "★ Saved", exact: true })).toBeVisible();
});

test("chart values remain accessible and official warnings remain visible", async ({ page }) => {
  await page.route("**/api/hazard/heat/*.json", route => route.fulfill({ json: {
    ...heatFixture(), official_advisory: { active: true, headline: "Test official warning", url: "https://www.weather.gov/sgx/" },
  } }));
  await page.goto("/hazard/heat/?place=imperial-beach");
  await expect(page.getByRole("heading", { name: "Heat · Imperial Beach", exact: true })).toBeVisible();
  await expect(page.getByText("NWS: Test official warning")).toBeVisible();
  await expect(page.getByRole("img", { name: /Chart in °F/ })).toBeVisible();
  await page.getByText("View chart data (2 points)", { exact: true }).click();
  const table = page.getByRole("table", { name: /°F · timestamps/ });
  await expect(table.getByRole("cell", { name: "85", exact: true })).toBeVisible();
  await expect(table.getByRole("cell", { name: "90", exact: true })).toBeVisible();
});

test("a future forecast never becomes today's verdict", async ({ page }) => {
  const fixture = heatFixture();
  await page.route("**/api/outlook/*.json", route => route.fulfill({ json: {
    place: QA_PLACES[0], updated_at: fixture.run_ts,
    tiles: QA_TILES.map(t => t === "heat" ? { ...fixture, days: fixture.days.slice(1) } : emptyTile(t)),
  } }));
  await page.goto("/?place=imperial-beach");
  const heat = page.getByRole("region", { name: "Heat", exact: true });
  await expect(heat.getByRole("button", { name: /^Heat/ })).toContainText("No forecast for today");
  await expect(heat.getByText("Next available forecast: Sun, Oct 25")).toBeVisible();
});

for (const width of [320, 390, 768, 1440]) {
  test(`all major screens fit a ${width}px viewport`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    for (const path of ["/", "/map/", "/hazard/water/", "/track-record/", "/data/"]) {
      await page.goto(`${path}?place=imperial-beach`);
      await expect(page.locator("main h1")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), path).toBe(true);
    }
  });
}

for (const path of ["/", "/map/", "/hazard/heat/", "/track-record/", "/data/"]) {
  test(`WCAG A/AA automated accessibility check: ${path}`, async ({ page }) => {
    if (path === "/hazard/heat/") await page.route("**/api/hazard/heat/*.json", route => route.fulfill({ json: heatFixture() }));
    await page.goto(`${path}?place=imperial-beach`);
    await expect(page.locator("main h1")).toBeVisible();
    // Wait for actual content rather than auditing only the loading state.
    if (path === "/") await expect(page.locator(".hazard-card")).toHaveCount(5);
    if (path === "/map/") await expect(page.getByRole("region", { name: "Selected neighborhood" })).toBeVisible();
    if (path === "/hazard/heat/") await expect(page.getByText("View chart data (2 points)")).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    expect(results.violations).toEqual([]);
  });
}
