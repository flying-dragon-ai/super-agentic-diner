import { chromium } from "./frontend/node_modules/playwright/index.mjs";

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.goto("http://127.0.0.1:8022/3d/scene", { waitUntil: "domcontentloaded", timeout: 30000 });
await page.waitForTimeout(3000);

const result = await page.evaluate(() => {
  const nodes = Array.from(document.querySelectorAll("div,button,span"));
  const label = nodes.find((el) =>
    (el.textContent || "").trim().startsWith("💬 AI 店长点单（匿名 #"),
  );
  const ancestry = [];
  let cursor = label;
  while (cursor && ancestry.length < 6) {
    const rect = cursor.getBoundingClientRect();
    ancestry.push({
      tag: cursor.tagName,
      text: (cursor.textContent || "").trim().slice(0, 80),
      display: getComputedStyle(cursor).display,
      visibility: getComputedStyle(cursor).visibility,
      width: rect.width,
      height: rect.height,
    });
    cursor = cursor.parentElement;
  }
  const orderButtons = Array.from(document.querySelectorAll("button")).filter((el) =>
    (el.textContent || "").includes("点单"),
  );
  const isVisible = (el) => {
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  };
  return {
    url: location.href,
    title: document.title,
    label_found: Boolean(label),
    label_ancestry: ancestry,
    order_button_count: orderButtons.length,
    visible_order_button_count: orderButtons.filter(isVisible).length,
    body_text_has_order_panel: (document.body.innerText || "").includes("AI 店长点单"),
  };
});

console.log(JSON.stringify(result));
await browser.close();
