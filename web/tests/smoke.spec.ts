import { expect, test } from "@playwright/test";

const WORDS = /Low|Moderate|High|Very high|Good|Don't swim|Swim with caution|Coming soon|No |Higher than usual tide|Minor coastal flooding|Moderate coastal flooding|Inland|Not rated|heat risk/;

for (const place of ["imperial-beach", "la-jolla"]) {
  test(`Today renders five hazard rows with text for ${place}`, async ({ page }) => {
    await page.goto(`/?place=${place}`);
    const rows = page.locator("main section");
    await expect(rows).toHaveCount(5);
    for (const name of ["Water", "Air", "Heat", "Flood", "Fire"]) await expect(page.getByText(name, { exact: true })).toBeVisible();
    for (let i = 0; i < 5; i++) await expect(rows.nth(i)).toContainText(WORDS);
  });
}
