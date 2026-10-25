import { expect, test } from "@playwright/test";
import { emptyTile, heatFixture, mockApi, QA_NOW, QA_PLACES, QA_TILES } from "./fixtures";

test.beforeEach(async ({ page }) => { await mockApi(page); });

test("homepage introduction leads into the selected neighborhood and expandable forecasts", async ({ page }) => {
  await page.route("**/api/outlook/*.json", route => route.fulfill({ json: {
    place: QA_PLACES[0], updated_at: QA_NOW,
    tiles: QA_TILES.map(tile => tile === "heat" ? heatFixture() : emptyTile(tile)),
  } }));
  await page.goto("/?place=imperial-beach");
  await expect(page.getByRole("main").getByRole("heading", { level: 1 })).toHaveCount(1);
  await page.getByRole("link", { name: "See your local outlook", exact: true }).click();
  await expect(page).toHaveURL(/place=imperial-beach#local-outlook/);
  const heat = page.getByRole("region", { name: "Heat", exact: true });
  await heat.getByRole("button").click();
  await expect(heat.getByRole("button")).toHaveAttribute("aria-expanded", "true");
  await heat.getByRole("link", { name: "Full heat forecast", exact: true }).click();
  await expect(page).toHaveURL(/hazard\/heat\/\?place=imperial-beach/);
  await expect(page.getByRole("heading", { name: "Heat · Imperial Beach", exact: true })).toBeVisible();
});

test("a direct report link reaches the form after neighborhood hydration", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/places.json", async route => {
    await new Promise(resolve => setTimeout(resolve, 150));
    await route.fulfill({ json: QA_PLACES });
  });
  await page.goto("/map/?place=imperial-beach&hazard=water#map-report");
  const report = page.getByRole("region", { name: "Selected neighborhood", exact: true });
  await expect(report.getByRole("heading", { name: "Imperial Beach", exact: true })).toBeVisible();
  await expect.poll(async () => report.evaluate(element => element.getBoundingClientRect().top)).toBeLessThan(500);
  const top = await report.evaluate(element => element.getBoundingClientRect().top);
  const headerBottom = await page.locator(".app-header").evaluate(element => element.getBoundingClientRect().bottom);
  expect(top).toBeGreaterThanOrEqual(headerBottom);
});

test("chart values can be explored with the keyboard without using the pointer", async ({ page }) => {
  await page.route("**/api/hazard/heat/*.json", route => route.fulfill({ json: heatFixture() }));
  await page.goto("/hazard/heat/?place=imperial-beach");
  const inspector = page.getByRole("slider", { name: "Inspect chart point", exact: true });
  await inspector.fill("1");
  await expect(page.locator(".chart-inspector output")).toContainText("85 °F");
  await expect(page.locator(".chart-inspector output")).toContainText("High end 90 °F");
  await inspector.press("Home");
  await expect(page.locator(".chart-inspector output")).toContainText("79 °F");
});

test("reduced motion leaves the redesigned homepage fully usable without entrance animation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?place=imperial-beach");
  await expect(page.locator(".hazard-card")).toHaveCount(4);
  expect(await page.locator(".home-hero").evaluate(element => getComputedStyle(element).animationName)).toBe("none");
  await page.getByRole("button", { name: "Change place", exact: true }).click();
  await expect(page.getByRole("searchbox", { name: "Neighborhood or ZIP", exact: true })).toBeVisible();
});
