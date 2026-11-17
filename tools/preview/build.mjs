/** Bundles the panel with stubbed Decky modules (see mock-ui.tsx, mock-api.ts). */
import * as esbuild from "esbuild";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const modules = path.join(here, "node_modules");
if (!fs.existsSync(path.join(modules, "react"))) {
  console.error("Run:  cd tools/preview && npm install && npx playwright install chromium");
  process.exit(1);
}

await esbuild.build({
  entryPoints: [path.join(here, "preview.tsx")],
  bundle: true,
  outfile: path.join(here, "preview.js"),
  jsx: "automatic",
  alias: {
    "@decky/api": path.join(here, "mock-api.ts"),
    "@decky/ui": path.join(here, "mock-ui.tsx"),
    "react-icons/fa": path.join(here, "../../node_modules/react-icons/fa/index.mjs"),
    react: path.join(modules, "react"),
    "react/jsx-runtime": path.join(modules, "react/jsx-runtime"),
    "react-dom": path.join(modules, "react-dom"),
    "react-dom/client": path.join(modules, "react-dom/client.js"),
  },
  logLevel: "warning",
});
console.log("preview.js built");
