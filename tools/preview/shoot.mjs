/**
 * Screenshots of the panel (panel.png) and of a plugin's dialog (modal.png),
 * plus a click through install / update. Exits 1 on a console error.
 */
import { chromium } from "playwright";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 330, height: 800 }, deviceScaleFactor: 2 });
const errors = [];
const calls = [];
page.on("console", (m) => {
  if (m.type() === "error") errors.push(m.text());
  if (m.text().startsWith("[DeckyBackend]")) calls.push(m.text());
});
page.on("pageerror", (e) => errors.push(String(e)));

await page.goto(`file://${path.join(here, "index.html")}`);
await page.locator("text=Updates (1)").waitFor();
await page.waitForTimeout(200);
await page.screenshot({ path: path.join(here, "panel.png"), fullPage: true });

// Install from a link: Decky's installer gets a file:// zip and a sha256.
await page.locator(".qam-input").first().fill("lauridskern/decky-rom-store");
await page.locator("text=Install latest release").click();
await page.locator("text=confirm in Decky's dialog").waitFor();

// Update one.
await page.locator("text=Update to v1.18.2").click();
await page.locator("text=Confirm the update in Decky's dialog.").waitFor();

// A plugin's dialog.
await page.setViewportSize({ width: 800, height: 600 });
await page.locator(".qam-item.field.focusable", { hasText: "ROM-Store" }).click();
await page.locator(".modal").waitFor();
await page.screenshot({ path: path.join(here, "modal.png") });

console.log("Decky calls:");
for (const c of calls) console.log("  " + c);
console.log(`console errors: ${errors.length}`);
for (const e of errors) console.log("  " + e);
await browser.close();
process.exit(errors.length || calls.length !== 2 ? 1 : 0);
