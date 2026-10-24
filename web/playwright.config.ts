import { defineConfig } from "@playwright/test";

// Serves the static export (with HTTP range support for the PMTiles basemap) and runs the smoke test.
export default defineConfig({
  testDir: "tests",
  webServer: { command: "npx --yes http-server@14.1.1 out -p 4399 -a 127.0.0.1 -s", url: "http://127.0.0.1:4399", reuseExistingServer: true },
  use: { baseURL: "http://127.0.0.1:4399" },
});
