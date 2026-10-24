import { defineConfig } from "@playwright/test";

// Serves the static export (with HTTP range support for the PMTiles basemap) and runs the smoke test.
export default defineConfig({
  testDir: "tests",
  testMatch: "**/*.spec.ts",
  forbidOnly: Boolean(process.env.CI),
  workers: process.env.CI ? 2 : undefined,
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "firefox", use: { browserName: "firefox" } },
    { name: "webkit", use: { browserName: "webkit" } },
  ],
  webServer: { command: "npx --yes http-server@14.1.1 out -p 4399 -a 127.0.0.1 -s", url: "http://127.0.0.1:4399", reuseExistingServer: !process.env.CI },
  use: { baseURL: "http://127.0.0.1:4399", locale: "en-US", timezoneId: "America/Los_Angeles", trace: "retain-on-failure", screenshot: "only-on-failure" },
});
