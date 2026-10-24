// Serve the installed MapLibre module worker intact; bundler URL rewriting can otherwise point it at HTML.
import { copyFileSync, mkdirSync } from "node:fs";
const source = "node_modules/maplibre-gl";
mkdirSync("public/map-assets", { recursive: true });
for (const name of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"])
  copyFileSync(`${source}/dist/${name}`, `public/map-assets/${name}`);
copyFileSync(`${source}/LICENSE.txt`, "public/map-assets/MAPLIBRE-LICENSE.txt");
