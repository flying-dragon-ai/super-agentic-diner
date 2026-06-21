// Ported from Claw3D retro-office core/persistence.ts. Coffee keeps only the
// save/load + namespace + layout-migration-flag mechanism; Claw3D's per-room
// migration keys (gym/qa/server/phone/sms) are out of scope for a single cafe.
import { LAYOUT_MIGRATION_KEY, STORAGE_KEY } from "./constants";
import type { FurnitureItem } from "./types";
import { getOfficeLayout, saveOfficeLayout } from "../../net/api";

const resolveStorageKey = (key: string, namespace = "default") =>
  namespace === "default" ? key : `${key}:${namespace}`;

export const saveFurniture = (items: FurnitureItem[], namespace = "default") => {
  try {
    localStorage.setItem(
      resolveStorageKey(STORAGE_KEY, namespace),
      JSON.stringify(items),
    );
  } catch {
    /* ignore quota / private mode */
  }
};

export const loadFurniture = (namespace = "default"): FurnitureItem[] | null => {
  try {
    const raw = localStorage.getItem(resolveStorageKey(STORAGE_KEY, namespace));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    // B3: accept an empty array — a user who deliberately deleted every piece
    // should stay empty on refresh, not be restored to the default layout.
    return Array.isArray(parsed) ? (parsed as FurnitureItem[]) : null;
  } catch {
    return null;
  }
};

// One-shot layout-migration flags. materializeDefaults() uses these so that a
// previously saved editor layout can be force-refreshed to the latest default
// layout without losing user edits on subsequent loads.
export const hasLayoutMigrationApplied = (namespace = "default") => {
  try {
    return (
      localStorage.getItem(resolveStorageKey(LAYOUT_MIGRATION_KEY, namespace)) ===
      "1"
    );
  } catch {
    return false;
  }
};

export const markLayoutMigrationApplied = (namespace = "default") => {
  try {
    localStorage.setItem(resolveStorageKey(LAYOUT_MIGRATION_KEY, namespace), "1");
  } catch {
    /* ignore */
  }
};

// ---------------------------------------------------------------------------
// Server-side layout (authoritative, global singleton). localStorage stays as
// an instant cache + offline fallback. Both calls are best-effort: failures
// swallow + warn so the editor degrades to local/default instead of blocking
// the scene from rendering.
// ---------------------------------------------------------------------------

export async function fetchServerLayout(): Promise<FurnitureItem[] | null> {
  try {
    const res = await getOfficeLayout();
    return Array.isArray(res.items) && res.items.length > 0
      ? (res.items as FurnitureItem[])
      : null;
  } catch (e) {
    console.warn("[layout] server fetch failed, using local fallback", e);
    return null;
  }
}

export async function pushServerLayout(items: FurnitureItem[]): Promise<void> {
  try {
    await saveOfficeLayout(items);
  } catch (e) {
    console.warn("[layout] server push failed (kept locally only)", e);
  }
}
