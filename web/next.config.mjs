import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

// Python and Next share the repository-root .env described in the README.
const envFile = resolve(dirname(fileURLToPath(import.meta.url)), "../.env");
if (existsSync(envFile)) process.loadEnvFile(envFile);

/** Static export: the hourly job renders the API to public/api, so the site needs no server. */
export default {
  output: "export", trailingSlash: true, images: { unoptimized: true },
  turbopack: { root: dirname(fileURLToPath(import.meta.url)) },
};
