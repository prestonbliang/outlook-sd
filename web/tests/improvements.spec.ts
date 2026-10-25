import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { emptyTile, heatFixture, mockApi, QA_NOW, QA_PLACES, QA_TILES } from "./fixtures";

test.beforeEach(async ({ page }) => { await mockApi(page); });

test("planning focus persists and dated forecasts open the matching map", async ({ page }) => {
  await page.route("**/api/outlook/*.json", route => route.fulfill({ json: {
    place: QA_PLACES[0], updated_at: QA_NOW, tiles: QA_TILES.map(t => t === "heat" ? heatFixture() : emptyTile(t)),
  } }));
  await page.goto("/?place=imperial-beach");
  const brief = page.getByRole("region", { name: "Plan the next three days" });
  await expect(brief.locator(".planning-day").first()).toContainText("1 hazard needs attention");
  await brief.getByRole("button", { name: "Beach visit", exact: true }).click();
  await expect(brief.getByText("Choose hazards (3)")).toBeVisible();
  await page.reload();
  await expect(brief.getByRole("button", { name: "Beach visit", exact: true })).toHaveAttribute("aria-pressed", "true");
  await brief.locator(".planning-day").nth(1).getByText("View forecasts", { exact: true }).click();
  await brief.locator(".planning-day").nth(1).getByRole("link", { name: "Heat", exact: true }).click();
  await expect(page).toHaveURL(/place=imperial-beach&hazard=heat&date=2026-10-25/);
  await expect(page.getByRole("radio", { name: /Sun, Oct 25/ })).toBeChecked();
});

test("source expiry updates an open page and removes a stale compound warning", async ({ page }) => {
  const source = [{ name: "Test weather", reference_at: QA_NOW, max_age_hours: 1 }];
  const high = (tile: string) => ({ ...emptyTile(tile), run_ts: QA_NOW, source_checks: source,
    days: [{ date: "2026-10-24", value: 1, level: "high", verdict: "High" }] });
  await page.route("**/api/outlook/*.json", route => route.fulfill({ json: {
    place: QA_PLACES[0], updated_at: QA_NOW, tiles: QA_TILES.map(t => t === "heat" || t === "fire" ? high(t) : emptyTile(t)),
  } }));
  await page.goto("/?place=imperial-beach");
  await expect(page.getByRole("note").filter({ hasText: "Two hazards at once" })).toBeVisible();
  await page.clock.setFixedTime(new Date("2026-10-24T19:01:00Z"));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("region", { name: "Heat", exact: true })).toContainText("data needs updating");
  await expect(page.getByRole("note").filter({ hasText: "Two hazards at once" })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Plan the next three days" }).locator(".planning-day").first()).toContainText("Updates needed");
});

test("saved comparisons load on demand, preserve successful rows, and recover one failed place", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("outlook-sd-watchlist", JSON.stringify(["imperial-beach", "la-jolla"])));
  let laJollaRequests = 0, fail = true;
  await page.route("**/api/outlook/*.json", route => {
    const place = route.request().url().includes("la-jolla") ? QA_PLACES[1] : QA_PLACES[0];
    if (place.id === "la-jolla") { laJollaRequests++; if (fail) return route.fulfill({ status: 404 }); }
    return route.fulfill({ json: { place, updated_at: QA_NOW, tiles: QA_TILES.map(t => t === "heat" ? heatFixture() : emptyTile(t)) } });
  });
  await page.goto("/?place=imperial-beach");
  await expect(page.getByRole("button", { name: "Compare saved places", exact: true })).toBeVisible();
  expect(laJollaRequests).toBe(0);
  await page.getByRole("button", { name: "Compare saved places", exact: true }).click();
  const comparison = page.getByRole("region", { name: "Saved neighborhood forecast comparison" });
  await expect(comparison.getByRole("row").filter({ hasText: "Imperial Beach" })).toContainText("Moderate");
  await expect(comparison.getByRole("row").filter({ hasText: "La Jolla" })).toContainText("not available yet");
  fail = false;
  await page.getByRole("button", { name: "Refresh saved forecasts" }).click();
  await expect(comparison.getByRole("row").filter({ hasText: "La Jolla" })).toContainText("Moderate");
  const accessibility = await new AxeBuilder({ page }).include(".saved-comparison").withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(accessibility.violations).toEqual([]);
});

test("yesterday's elevated ratings leave the planning banner at Pacific midnight", async ({ page }) => {
  const issued = "2026-10-25T06:30:00Z";
  await page.clock.setFixedTime(new Date(issued));
  await page.route("**/api/outlook/*.json", route => route.fulfill({ json: {
    place: QA_PLACES[0], updated_at: issued, tiles: QA_TILES.map(tile => ({ ...emptyTile(tile), run_ts: issued,
      days: [{ date: "2026-10-24", value: 1, level: "high", verdict: "High" },
        { date: "2026-10-25", value: 0, level: "low", verdict: "Low" }],
    })),
  } }));
  await page.goto("/?place=imperial-beach");
  const banner = page.getByRole("note").filter({ hasText: "hazards at once" });
  await expect(banner).toBeVisible();
  await page.clock.setFixedTime(new Date("2026-10-25T07:01:00Z"));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(banner).toHaveCount(0);
});

test("missing scenarios explain both unavailable comparisons", async ({ page }) => {
  await page.route("**/api/scenarios.json", route => route.fulfill({ json: { flow: null, sea_level: null } }));
  await page.goto("/what-if/?place=imperial-beach");
  await expect(page.getByRole("heading", { name: "River-flow scenario unavailable" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sea-level scenario unavailable" })).toBeVisible();
  await expect(page.getByRole("slider")).toHaveCount(0);
});

test("scenario fetch errors can be retried without reloading the page", async ({ page }) => {
  let fail = true;
  await page.route("**/api/scenarios.json", route => fail ? route.fulfill({ status: 503 }) : route.fulfill({ json: { flow: null, sea_level: null } }));
  await page.goto("/what-if/?place=imperial-beach");
  const error = page.getByRole("main").getByRole("alert");
  await expect(error).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "Try loading scenarios again" }).click();
  await expect(page.getByRole("heading", { name: "River-flow scenario unavailable" })).toBeVisible();
  await expect(error).toHaveCount(0);
});

test("zero-baseline scenarios show zero-width bars and valid available controls", async ({ page }) => {
  await page.route("**/api/scenarios.json", route => route.fulfill({ json: {
    flow: { period: "Test record", samples: 100, no_cap_unsafe_share: 0, caps: [{ cap_mgd: 0, unsafe_share: 0 }, { cap_mgd: 5, unsafe_share: 0 }] },
    sea_level: null,
  } }));
  await page.goto("/what-if/?place=imperial-beach");
  await expect(page.locator(".compare-bar.now")).toHaveAttribute("style", /width: 0%/);
  await expect(page.locator(".compare-bar.then")).toHaveAttribute("style", /width: 0%/);
  await expect(page.getByRole("slider")).toHaveAttribute("max", "5");
});

test("Data explains forecast publication separately from live community reads", async ({ page }) => {
  await page.goto("/data/?place=imperial-beach");
  const status = page.getByRole("region", { name: "What is connected?" });
  await expect(status).toContainText("Forecast snapshot:");
  await expect(status).toContainText("Community observations:");
  await status.getByText("Publication details", { exact: true }).click();
  await expect(status.getByText("1234567", { exact: true })).toBeVisible();
});

test("a recorded warning remains visible when its current status is unknown", async ({ page }) => {
  await page.route("**/api/hazard/flood/*.json", route => route.fulfill({ json: {
    ...emptyTile("flood"), place: QA_PLACES[0], window: null, series: null, metrics: null, what_to_do: "Check official sources.",
    official_advisory: { active: null, headline: "Test unconfirmed warning", url: "https://www.weather.gov/sgx/",
      check: { name: "NWS", reference_at: QA_NOW, max_age_hours: 3 } },
  } }));
  await page.goto("/hazard/flood/?place=imperial-beach");
  await expect(page.getByRole("note")).toContainText("NWS: Test unconfirmed warning");
  await expect(page.getByRole("note")).toContainText("Last recorded warning");
  await expect(page.getByText("Official alert status could not be confirmed.", { exact: false })).toBeVisible();
});

test("an open detail page advances its verdict and advice together at Pacific midnight", async ({ page }) => {
  await page.route("**/api/hazard/heat/*.json", route => route.fulfill({ json: {
    ...heatFixture(), what_to_do: "Test first-day guidance.", what_to_do_by_date: {
      "2026-10-24": "Test first-day guidance.", "2026-10-25": "Test next-day guidance.",
    },
  } }));
  await page.goto("/hazard/heat/?place=imperial-beach");
  await expect(page.getByText("Test first-day guidance.", { exact: true })).toBeVisible();
  await page.clock.setFixedTime(new Date("2026-10-25T07:01:00Z"));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByText("Low · Today", { exact: true })).toBeVisible();
  await expect(page.getByText("Test next-day guidance.", { exact: true })).toBeVisible();
  await expect(page.getByText("Test first-day guidance.", { exact: true })).toHaveCount(0);
});

test("an implicit map day follows Pacific midnight without changing an explicit shared day", async ({ page }) => {
  await page.goto("/map/?place=imperial-beach");
  await expect(page.getByRole("radio", { name: "Today", exact: true })).toBeChecked();
  await page.clock.setFixedTime(new Date("2026-10-25T07:01:00Z"));
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("radio", { name: "Today", exact: true })).toBeChecked();
  await page.goto("/map/?place=imperial-beach&date=2026-10-24");
  await expect(page.getByRole("radio", { name: /Sat, Oct 24/ })).toBeChecked();
});
