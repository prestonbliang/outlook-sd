import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

/** Static export: the hourly job renders the API to public/api, so the site needs no server. */
export default {
  output: "export", trailingSlash: true, images: { unoptimized: true },
  turbopack: { root: dirname(fileURLToPath(import.meta.url)) },
};
