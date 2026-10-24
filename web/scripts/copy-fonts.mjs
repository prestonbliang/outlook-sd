// Public Sans (400, 600) from @uswds/uswds → public/fonts, so the font is self-hosted.
import { copyFileSync, mkdirSync } from "node:fs";
const src = "node_modules/@uswds/uswds/dist/fonts/public-sans";
mkdirSync("public/fonts", { recursive: true });
for (const w of ["Regular", "SemiBold"]) copyFileSync(`${src}/PublicSans-${w}.woff2`, `public/fonts/PublicSans-${w}.woff2`);
