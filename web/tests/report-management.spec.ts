import { expect, test, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import AxeBuilder from "@axe-core/playwright";
import { mockApi, QA_NOW } from "./fixtures";

const browserId = "10000000-0000-4000-a000-000000000001";
const browserToken = "a".repeat(64);
const digest = (token: string) => createHash("sha256").update(token).digest("hex");
async function backend(page: Page, seeded = false) {
  await mockApi(page);
  if (seeded) await page.addInitScript(({ browserId, browserToken }) => {
    if (!localStorage.getItem("outlook-sd-client")) localStorage.setItem("outlook-sd-client", browserId);
    if (!localStorage.getItem("outlook-sd-report-secret")) localStorage.setItem("outlook-sd-report-secret", browserToken);
  }, { browserId, browserToken });
  const state = {
    active: seeded, everSent: seeded, removalStatus: 200, loseResponse: false, ownerStatus: 200,
    write: seeded ? { client_id: browserId, withdrawal_hash: digest(browserToken) } as Record<string, unknown> : undefined,
  };
  await page.route("**/rest/v1/reports", async route => {
    if (state.everSent) return route.fulfill({ status: 400, json: { message: "You already sent this report for this place in the last 6 hours" } });
    state.write = route.request().postDataJSON(); state.active = true; state.everSent = true;
    await route.fulfill({ status: 201, body: "" });
  });
  await page.route("**/rest/v1/rpc/report_summary", route => route.fulfill({ json: state.active ? [{
    place_id: "imperial-beach", hazard: "water", total: 1, reporters: 1, problem_reports: 1, clear_reports: 0,
    last_report_at: QA_NOW, kinds: { water_debris: 1 },
  }] : [] }));
  await page.route("**/rest/v1/rpc/my_report_options", route => {
    const body = route.request().postDataJSON();
    const owns = body.browser_id === state.write?.client_id && digest(body.browser_token) === state.write?.withdrawal_hash;
    return route.fulfill({ status: state.ownerStatus, json: state.ownerStatus === 200 && owns && state.active ? [{
      place_id: "imperial-beach", hazard: "water", kind: "water_debris", created_at: QA_NOW,
    }] : [] });
  });
  await page.route("**/rest/v1/rpc/withdraw_report_option", async route => {
    const body = route.request().postDataJSON();
    const owns = body.browser_id === state.write?.client_id && digest(body.browser_token) === state.write?.withdrawal_hash
      && body.target_place === "imperial-beach" && body.target_kind === "water_debris";
    if (state.removalStatus !== 200) return route.fulfill({ status: state.removalStatus, json: {} });
    if (owns) state.active = false;
    if (state.loseResponse) { state.loseResponse = false; return route.abort("failed"); }
    return route.fulfill({ json: owns });
  });
  return state;
}
const reportBox = (page: Page) => page.getByRole("region", { name: "What do you see in Imperial Beach?", exact: true });

test("saving, reloading and removing an owned observation refreshes the community summary", async ({ page }, testInfo) => {
  const state = await backend(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/map/?place=imperial-beach");
  await reportBox(page).getByRole("button", { name: "Floating litter or debris", exact: true }).click();
  await expect(reportBox(page).getByText(/was saved/)).toBeVisible();
  const token = await page.evaluate(() => localStorage.getItem("outlook-sd-report-secret"));
  expect(token).toMatch(/^[0-9a-f]{64}$/);
  expect(state.write?.withdrawal_hash).toBe(digest(token!));
  expect(state.write).not.toHaveProperty("browser_token");
  await page.reload();
  const mine = reportBox(page).getByRole("region", { name: "Your active observations" });
  const remove = mine.getByRole("button", { name: "Remove Floating litter or debris", exact: true });
  await expect(remove).toBeVisible();
  await expect(reportBox(page).getByRole("button", { name: "Floating litter or debris", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(reportBox(page).getByRole("region", { name: "Summary of recent observations" })).toContainText("floating litter or debris");
  const axe = await new AxeBuilder({ page }).include(".report-box").withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(axe.violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await reportBox(page).screenshot({ path: testInfo.outputPath("community-observations.png") });
  await remove.focus(); await page.keyboard.press("Enter");
  await expect(reportBox(page).getByText("Your observation was removed from the community summary.")).toBeVisible();
  await expect(mine.getByText(/No active observations/)).toBeVisible();
  await expect(reportBox(page).getByRole("button", { name: "Floating litter or debris", exact: true })).toBeFocused();
  await expect(reportBox(page).getByRole("region", { name: "Summary of recent observations" })).toHaveCount(0);
  await reportBox(page).getByRole("button", { name: "Floating litter or debris", exact: true }).click();
  await expect(reportBox(page).getByRole("alert")).toContainText("You already sent this report");
});

test("a selected option can be toggled off without finding its separate Remove control", async ({ page }) => {
  await backend(page, true);
  await page.goto("/map/?place=imperial-beach");
  const option = reportBox(page).getByRole("button", { name: "Floating litter or debris", exact: true });
  await expect(option).toHaveAttribute("aria-pressed", "true");
  await option.click();
  await expect(reportBox(page).getByText("Your observation was removed from the community summary.")).toBeVisible();
  await expect(option).toHaveAttribute("aria-pressed", "false");
});

test("a failed removal retains the choice and never claims success", async ({ page }) => {
  const state = await backend(page, true); state.removalStatus = 503;
  await page.goto("/map/?place=imperial-beach");
  const remove = reportBox(page).getByRole("button", { name: "Remove Floating litter or debris", exact: true });
  await remove.click();
  await expect(reportBox(page).getByRole("alert")).toContainText("Could not remove");
  await expect(remove).toBeEnabled();
  await expect(reportBox(page).getByText(/was removed from/)).toHaveCount(0);
  expect(state.active).toBe(true);
});

test("a lost removal response can be retried safely", async ({ page }) => {
  const state = await backend(page, true); state.loseResponse = true;
  await page.goto("/map/?place=imperial-beach");
  const remove = reportBox(page).getByRole("button", { name: "Remove Floating litter or debris", exact: true });
  await remove.click();
  await expect(reportBox(page).getByRole("alert")).toContainText("Could not confirm removal");
  await expect(reportBox(page).getByText(/was removed from/)).toHaveCount(0);
  await remove.click();
  await expect(reportBox(page).getByText("Your observation was removed from the community summary.")).toBeVisible();
});

test("ownership list errors offer retry rather than claiming there are no reports", async ({ page }) => {
  const state = await backend(page, true); state.ownerStatus = 503;
  await page.goto("/map/?place=imperial-beach");
  const mine = reportBox(page).getByRole("region", { name: "Your active observations" });
  await expect(mine.getByText(/Your observations could not load/)).toBeVisible();
  await expect(mine.getByText(/No active observations/)).toHaveCount(0);
  state.ownerStatus = 200;
  await mine.getByRole("button", { name: "Retry your observations" }).click();
  await expect(mine.getByRole("button", { name: "Remove Floating litter or debris" })).toBeVisible();
});

test("a different private token cannot recover or remove another browser's observations", async ({ page }) => {
  await backend(page, true);
  await page.addInitScript(() => { localStorage.setItem("outlook-sd-report-secret", "b".repeat(64)); });
  await page.goto("/map/?place=imperial-beach");
  const mine = reportBox(page).getByRole("region", { name: "Your active observations" });
  await expect(mine.getByText(/No active observations/)).toBeVisible();
  await expect(mine.getByRole("button", { name: /^Remove / })).toHaveCount(0);
  await expect(reportBox(page).getByRole("region", { name: "Summary of recent observations" })).toContainText("floating litter or debris");
});

test("older databases preserve working submissions without claiming removal is available", async ({ page }) => {
  await mockApi(page);
  await page.route("**/rest/v1/rpc/report_features", route => route.fulfill({ status: 404, json: {} }));
  let payload: Record<string, unknown> | undefined;
  await page.route("**/rest/v1/reports", async route => { payload = route.request().postDataJSON(); await route.fulfill({ status: 201, body: "" }); });
  await page.goto("/map/?place=imperial-beach");
  await reportBox(page).getByRole("button", { name: "Floating litter or debris", exact: true }).click();
  await expect(reportBox(page).getByText(/was saved/)).toBeVisible();
  expect(Object.keys(payload!).sort()).toEqual(["client_id", "hazard", "kind", "place_id"]);
  await expect(reportBox(page).getByText(/Report removal is unavailable/)).toBeVisible();
  await expect(reportBox(page).getByRole("region", { name: "Your active observations" })).toHaveCount(0);
});

test("a safeguards outage blocks unmanageable submissions and can recover", async ({ page }) => {
  await mockApi(page);
  let recovered = false;
  let writes = 0;
  await page.route("**/rest/v1/rpc/report_features", route => recovered
    ? route.fulfill({ json: { version: 1, withdrawal: true } }) : route.fulfill({ status: 503, json: {} }));
  await page.route("**/rest/v1/reports", async route => { writes++; await route.fulfill({ status: 201, body: "" }); });
  await page.goto("/map/?place=imperial-beach");
  const option = reportBox(page).getByRole("button", { name: "Floating litter or debris", exact: true });
  await expect(reportBox(page).getByText(/Reporting safeguards could not be checked/)).toBeVisible();
  await expect(option).toBeDisabled();
  expect(writes).toBe(0);
  recovered = true;
  await reportBox(page).getByRole("button", { name: "Retry reporting safeguards" }).click();
  await expect(option).toBeEnabled();
  await option.click();
  await expect(reportBox(page).getByText(/was saved/)).toBeVisible();
  expect(writes).toBe(1);
});

test("blocked storage prevents submissions rather than sending an unmanageable report", async ({ page }) => {
  const state = await backend(page);
  await page.addInitScript(() => { Storage.prototype.setItem = () => { throw new DOMException("Blocked", "SecurityError"); }; });
  await page.goto("/map/?place=imperial-beach");
  await reportBox(page).getByRole("button", { name: "Floating litter or debris", exact: true }).click();
  await expect(reportBox(page).getByRole("alert")).toContainText("Enable site storage");
  expect(state.everSent).toBe(false);
});

test("mixed reports get a plain-language account with counts as optional supporting detail", async ({ page }) => {
  await mockApi(page);
  await page.route("**/rest/v1/rpc/report_summary", route => route.fulfill({ json: [{
    place_id: "imperial-beach", hazard: "water", total: 3, reporters: 2, problem_reports: 2, clear_reports: 1,
    last_report_at: QA_NOW, kinds: { water_debris: 1, water_foam: 1, water_ok: 1 },
  }] }));
  await page.goto("/map/?place=imperial-beach");
  const summary = reportBox(page).getByRole("region", { name: "Summary of recent observations" });
  await expect(summary.getByRole("heading", { name: "Observations are mixed" })).toBeVisible();
  await expect(summary).toContainText("floating litter or debris and unusual foam");
  await expect(summary).toContainText("not verified people");
  await expect(reportBox(page).locator(".observation-counts")).not.toBeVisible();
  await reportBox(page).getByText("View observation counts", { exact: true }).click();
  await expect(reportBox(page).locator(".observation-counts")).toBeVisible();
});
