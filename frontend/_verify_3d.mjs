import { chromium } from "playwright-core";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const base = join(homedir(), "AppData", "Local", "ms-playwright");
let exe = null;
for (const c of ["chromium-1228", "chromium-1217"]) {
  const p = join(base, c, "chrome-win64", "chrome.exe");
  if (existsSync(p)) { exe = p; break; }
}
if (!exe) { console.error("chromium not found"); process.exit(2); }

const url = process.env.URL || "http://127.0.0.1:8000/3d/scene";
const browser = await chromium.launch({
  executablePath: exe,
  args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox"],
});
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
page.on("pageerror", (e) => errors.push("pageerror: " + (e.stack || String(e))));
page.on("requestfailed", (r) => errors.push("reqfail: " + r.url() + " " + (r.failure()?.errorText || "")));

await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
await page.waitForTimeout(6000);

const info = await page.evaluate(() => {
  const c = document.querySelector("canvas");
  const root = document.getElementById("root");
  return {
    hasCanvas: !!c,
    canvasW: c ? c.width : 0,
    canvasH: c ? c.height : 0,
    rootChildCount: root ? root.childElementCount : -1,
    bodyText: (document.body.innerText || "").slice(0, 200),
  };
});

await page.screenshot({ path: "_verify_3d.png" });
await browser.close();
console.log(JSON.stringify({ info, errors: errors.slice(0, 10) }, null, 2));
process.exit(errors.length || !info.hasCanvas ? 1 : 0);
