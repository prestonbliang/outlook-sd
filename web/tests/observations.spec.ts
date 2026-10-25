import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { KINDS, LEGACY_KINDS } from "../lib/community";
import { mockApi, QA_NOW } from "./fixtures";

test.beforeEach(async ({ page }) => { await mockApi(page); });

for (const hazard of ["water", "air", "heat", "flood", "fire"] as const) {
  test(`${hazard} offers all supported choices with accessible mobile controls`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/map/?place=imperial-beach&hazard=${hazard}`);
    const box = page.getByRole("region", { name: "What do you see in Imperial Beach?", exact: true });
    for (const option of KINDS[hazard]) await expect(box.getByRole("button", { name: option.label, exact: true })).toBeEnabled();
    await expect(box.locator(".observation-group").getByRole("button")).toHaveCount(KINDS[hazard].length);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    const results = await new AxeBuilder({ page }).include(".report-box").withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(results.violations).toEqual([]);
  });
}

test("a new observation saves its exact type and refreshes the summary", async ({ page }) => {
  let payload: Record<string, unknown> | undefined;
  await page.route("**/rest/v1/rpc/report_summary", route => route.fulfill({ json: payload ? [{
    place_id: "imperial-beach", hazard: "water", total: 1, reporters: 1, problem_reports: 1, clear_reports: 0,
    last_report_at: QA_NOW, kinds: { water_debris: 1 },
  }] : [] }));
  await page.route("**/rest/v1/reports", async route => {
    payload = route.request().postDataJSON();
    await route.fulfill({ status: 201, body: "" });
  });
  await page.goto("/map/?place=imperial-beach");
  const box = page.getByRole("region", { name: "What do you see in Imperial Beach?", exact: true });
  await box.getByRole("button", { name: "Floating litter or debris", exact: true }).click();
  await expect(box.getByText("Thanks. Your observation for Imperial Beach was saved.")).toBeVisible();
  await expect(box.getByRole("region", { name: "Summary of recent observations" })).toContainText("floating litter or debris");
  await box.getByText("View observation counts", { exact: true }).click();
  await expect(box.locator(".observation-counts")).toContainText("Floating litter or debris: 1");
  expect(payload?.kind).toBe("water_debris");
  expect(Object.keys(payload!).sort()).toEqual(["client_id", "hazard", "kind", "place_id", "withdrawal_hash"]);
});

for (const status of [404, 503]) {
  test(`options metadata HTTP ${status} preserves working original choices`, async ({ page }) => {
    await page.route("**/rest/v1/rpc/report_kinds", route => route.fulfill({ status, json: {} }));
    await page.goto("/map/?place=imperial-beach");
    const box = page.getByRole("region", { name: "What do you see in Imperial Beach?", exact: true });
    await expect(box.getByRole("button", { name: "Sewage smell or brown water", exact: true })).toBeVisible();
    await expect(box.getByRole("button")).toHaveCount(LEGACY_KINDS.filter(k => k.startsWith("water_")).length);
    await expect(box.getByRole("button", { name: "Floating litter or debris", exact: true })).toHaveCount(0);
  });
}

test("repeat rejection for a new type never claims success", async ({ page }) => {
  await page.route("**/rest/v1/reports", route => route.fulfill({ status: 400,
    json: { message: "You already sent this report for this place in the last 6 hours" } }));
  await page.goto("/map/?place=imperial-beach");
  const box = page.getByRole("region", { name: "What do you see in Imperial Beach?", exact: true });
  await box.getByRole("button", { name: "Unusual foam on the water", exact: true }).click();
  await expect(box.getByRole("alert")).toContainText("You already sent this report");
  await expect(box.getByText(/was saved/)).toHaveCount(0);
});
