import { chromium } from "playwright-core";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const browserRoot = join(homedir(), "AppData", "Local", "ms-playwright");
let executablePath = null;
for (const candidate of ["chromium-1228", "chromium-1217"]) {
  const path = join(browserRoot, candidate, "chrome-win64", "chrome.exe");
  if (existsSync(path)) {
    executablePath = path;
    break;
  }
}

if (!executablePath) {
  console.error("chromium not found");
  process.exit(2);
}

const url = process.env.URL || "http://localhost:5174/3d/scene";
const storageKey = "coffee-office-furniture-v1";
const migrationKey = "coffee-office-layout-migration-v1";
const autosaveWaitMs = 650;
const checks = [];
const errors = [];

const browser = await chromium.launch({
  executablePath,
  args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--no-sandbox"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

page.on("console", (message) => {
  if (message.type() === "error") errors.push(`console: ${message.text()}`);
});
page.on("pageerror", (error) => errors.push(`pageerror: ${error.stack || String(error)}`));
page.on("requestfailed", (request) =>
  errors.push(`reqfail: ${request.url()} ${request.failure()?.errorText || ""}`),
);

function summarize(item) {
  if (!item) return null;
  return {
    uid: item._uid,
    type: item.type,
    x: item.x,
    y: item.y,
    facing: item.facing ?? null,
    elevation: item.elevation ?? null,
  };
}

function record(label, ok, details = {}) {
  checks.push({ label, ok, details });
  if (!ok) {
    const error = new Error(label);
    error.details = details;
    throw error;
  }
}

async function waitForScene() {
  await page.waitForSelector("canvas", { timeout: 30000 });
  await page.waitForTimeout(1200);
}

async function waitForAutosave() {
  await page.waitForTimeout(autosaveWaitMs);
}

async function getLayout() {
  const raw = await page.evaluate((key) => localStorage.getItem(key), storageKey);
  return raw ? JSON.parse(raw) : [];
}

async function clearPersistedLayout() {
  await page.evaluate(
    ([layoutKey, layoutMigrationKey]) => {
      localStorage.removeItem(layoutKey);
      localStorage.removeItem(layoutMigrationKey);
    },
    [storageKey, migrationKey],
  );
  await page.reload({ waitUntil: "domcontentloaded", timeout: 30000 });
  await waitForScene();
  await waitForAutosave();
  return getLayout();
}

async function reloadAndGetLayout() {
  await page.reload({ waitUntil: "domcontentloaded", timeout: 30000 });
  await waitForScene();
  await waitForAutosave();
  return getLayout();
}

async function openEditor() {
  const editButton = page.getByRole("button", { name: /编辑$/ });
  await editButton.click({ timeout: 10000 });
  await page.waitForSelector('button[title="Plant"]', { timeout: 10000 });
}

async function placeItem(title, position = { x: 1000, y: 560 }) {
  const before = await getLayout();
  await page.locator(`button[title="${title}"]`).click({ timeout: 10000 });
  await page.locator("canvas").click({ position });
  await waitForAutosave();
  const after = await getLayout();
  const beforeUids = new Set(before.map((item) => item._uid));
  const selectedUid = await getSelectedUid();
  const addedItems = after.filter((candidate) => !beforeUids.has(candidate._uid));
  const item =
    (selectedUid ? after.find((candidate) => candidate._uid === selectedUid) : null) ??
    addedItems[addedItems.length - 1] ??
    null;
  record(`place ${title} autosaves`, Boolean(item), {
    beforeCount: before.length,
    afterCount: after.length,
    selectedUid,
    addedUids: addedItems.map((candidate) => candidate._uid),
  });
  return { before, after, item, position };
}

function findByUid(layout, uid) {
  return layout.find((item) => item._uid === uid) ?? null;
}

async function getSelectedUid() {
  const selectedLine = page.locator("div", { hasText: "已选中" }).first();
  await selectedLine.waitFor({ timeout: 10000 });
  const text = (await selectedLine.textContent()) ?? "";
  return text.match(/已选中\s*·\s*(\S+)/)?.[1] ?? null;
}

try {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  await waitForScene();

  const defaultLayout = await clearPersistedLayout();
  record("initial default layout autosaves", defaultLayout.length > 0, {
    defaultCount: defaultLayout.length,
  });

  await openEditor();

  const plant = await placeItem("Plant");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("PageUp");
  await page.keyboard.press("]");
  await waitForAutosave();

  const keyboardLayout = await getLayout();
  const keyboardItem = findByUid(keyboardLayout, plant.item._uid);
  record("keyboard move/elevate/rotate autosaves", Boolean(keyboardItem), {
    item: summarize(keyboardItem),
  });
  record(
    "keyboard values changed before reload",
    keyboardItem.x > plant.item.x &&
      (keyboardItem.elevation ?? 0) > (plant.item.elevation ?? 0) &&
      (keyboardItem.facing ?? 0) !== (plant.item.facing ?? 0),
    {
      before: summarize(plant.item),
      after: summarize(keyboardItem),
    },
  );

  const keyboardReloadLayout = await reloadAndGetLayout();
  const keyboardReloadItem = findByUid(keyboardReloadLayout, plant.item._uid);
  record(
    "keyboard changes survive reload",
    JSON.stringify(summarize(keyboardReloadItem)) === JSON.stringify(summarize(keyboardItem)),
    {
      beforeReload: summarize(keyboardItem),
      afterReload: summarize(keyboardReloadItem),
    },
  );

  await clearPersistedLayout();
  await openEditor();
  const table = await placeItem("Round Table", { x: 920, y: 560 });
  await page.getByRole("button", { name: /右/ }).click({ timeout: 10000 });
  await waitForAutosave();

  const panelMoveLayout = await getLayout();
  const panelMoveItem = findByUid(panelMoveLayout, table.item._uid);
  const panelMoved =
    panelMoveItem && (panelMoveItem.x !== table.item.x || panelMoveItem.y !== table.item.y);
  record("selected panel move autosaves", Boolean(panelMoved), {
    before: summarize(table.item),
    after: summarize(panelMoveItem),
  });

  const panelMoveReloadLayout = await reloadAndGetLayout();
  const panelMoveReloadItem = findByUid(panelMoveReloadLayout, table.item._uid);
  record(
    "selected panel move survives reload",
    JSON.stringify(summarize(panelMoveReloadItem)) === JSON.stringify(summarize(panelMoveItem)),
    {
      beforeReload: summarize(panelMoveItem),
      afterReload: summarize(panelMoveReloadItem),
    },
  );

  await clearPersistedLayout();
  await openEditor();
  const beanbag = await placeItem("Beanbag", { x: 1010, y: 590 });
  await page.keyboard.press("Delete");
  await waitForAutosave();
  const deleteKeyLayout = await getLayout();
  record("Delete key autosaves removal", !findByUid(deleteKeyLayout, beanbag.item._uid), {
    deletedUid: beanbag.item._uid,
    countAfterDelete: deleteKeyLayout.length,
  });
  const deleteKeyReloadLayout = await reloadAndGetLayout();
  record("Delete key removal survives reload", !findByUid(deleteKeyReloadLayout, beanbag.item._uid), {
    deletedUid: beanbag.item._uid,
  });

  await clearPersistedLayout();
  await openEditor();
  const deleteButtonPlant = await placeItem("Plant", { x: 1000, y: 560 });
  await page.getByRole("button", { name: /^删除$/ }).click({ timeout: 10000 });
  await waitForAutosave();
  const buttonDeleteLayout = await getLayout();
  record("delete button autosaves removal", !findByUid(buttonDeleteLayout, deleteButtonPlant.item._uid), {
    deletedUid: deleteButtonPlant.item._uid,
  });
  const buttonDeleteReloadLayout = await reloadAndGetLayout();
  record("delete button removal survives reload", !findByUid(buttonDeleteReloadLayout, deleteButtonPlant.item._uid), {
    deletedUid: deleteButtonPlant.item._uid,
  });

  const resetDefaultLayout = await clearPersistedLayout();
  await openEditor();
  const resetPlant = await placeItem("Plant", { x: 1000, y: 560 });
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: /恢复默认/ }).click({ timeout: 10000 });
  await waitForAutosave();
  const resetLayout = await getLayout();
  record("reset autosaves default layout", JSON.stringify(resetLayout) === JSON.stringify(resetDefaultLayout), {
    addedUid: resetPlant.item._uid,
    defaultCount: resetDefaultLayout.length,
    resetCount: resetLayout.length,
  });
  const resetReloadLayout = await reloadAndGetLayout();
  record("reset default layout survives reload", JSON.stringify(resetReloadLayout) === JSON.stringify(resetDefaultLayout), {
    defaultCount: resetDefaultLayout.length,
    reloadCount: resetReloadLayout.length,
  });

  await page.screenshot({ path: "_verify_editor_autosave.png" });
  await browser.close();

  console.log(
    JSON.stringify(
      {
        ok: checks.every((check) => check.ok),
        url,
        checks,
        errors: errors.slice(0, 12),
      },
      null,
      2,
    ),
  );
  process.exit(0);
} catch (error) {
  await page.screenshot({ path: "_verify_editor_autosave_failed.png" }).catch(() => {});
  await browser.close().catch(() => {});
  console.log(
    JSON.stringify(
      {
        ok: false,
        url,
        failed: error.message,
        details: error.details ?? null,
        checks,
        errors: errors.slice(0, 12),
      },
      null,
      2,
    ),
  );
  process.exit(1);
}
