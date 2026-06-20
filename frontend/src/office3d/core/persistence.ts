// Ported from Claw3D retro-office core/persistence.ts. Coffee keeps only the
// save/load + namespace + layout-migration-flag mechanism; Claw3D's per-room
// migration keys (gym/qa/server/phone/sms) are out of scope for a single cafe.
import { LAYOUT_MIGRATION_KEY, STORAGE_KEY } from "./constants";
import type { FurnitureItem } from "./types";

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
    return Array.isArray(parsed) && parsed.length > 0
      ? (parsed as FurnitureItem[])
      : null;
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
