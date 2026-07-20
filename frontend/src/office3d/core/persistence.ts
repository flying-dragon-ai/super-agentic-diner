// Ported from Claw3D retro-office core/persistence.ts. Coffee keeps only the
// save/load + namespace + layout-migration-flag mechanism; Claw3D's per-room
// migration keys (gym/qa/server/phone/sms) are out of scope for a single cafe.
import { LAYOUT_MIGRATION_KEY, STORAGE_KEY, STORAGE_META_KEY } from "./constants";
import type { FurnitureItem } from "./types";
import { getOfficeLayout, saveOfficeLayout } from "../../net/api";

const LEGACY_STORAGE_KEY = "coffee-office-furniture-v1";
const LEGACY_STORAGE_META_KEY = "coffee-office-furniture-meta-v1";

const resolveStorageKey = (key: string, namespace = "default") =>
  namespace === "default" ? key : `${key}:${namespace}`;

const loadStoredArray = (key: string, namespace: string): FurnitureItem[] | null => {
  const raw = localStorage.getItem(resolveStorageKey(key, namespace));
  if (!raw) return null;
  const parsed = JSON.parse(raw);
  // An empty array is intentional: a user may delete every scene item.
  return Array.isArray(parsed) ? (parsed as FurnitureItem[]) : null;
};

const loadStoredSavedAt = (key: string, namespace: string): string | null => {
  const raw = localStorage.getItem(resolveStorageKey(key, namespace));
  if (!raw) return null;
  const parsed = JSON.parse(raw);
  return typeof parsed?.savedAt === "string" ? parsed.savedAt : null;
};

export const saveFurniture = (items: FurnitureItem[], namespace = "default") => {
  try {
    localStorage.setItem(
      resolveStorageKey(STORAGE_KEY, namespace),
      JSON.stringify(items),
    );
    localStorage.setItem(
      resolveStorageKey(STORAGE_META_KEY, namespace),
      JSON.stringify({ savedAt: new Date().toISOString() }),
    );
  } catch {
    /* ignore quota / private mode */
  }
};

export const loadFurnitureSavedAt = (namespace = "default"): string | null => {
  try {
    const currentItems = loadStoredArray(STORAGE_KEY, namespace);
    if (currentItems !== null) {
      try {
        return loadStoredSavedAt(STORAGE_META_KEY, namespace);
      } catch {
        return null;
      }
    }
    return loadStoredSavedAt(LEGACY_STORAGE_META_KEY, namespace);
  } catch {
    try {
      return loadStoredSavedAt(LEGACY_STORAGE_META_KEY, namespace);
    } catch {
      return null;
    }
  }
};

export const loadFurniture = (namespace = "default"): FurnitureItem[] | null => {
  try {
    const current = loadStoredArray(STORAGE_KEY, namespace);
    if (current !== null) return current;
    // Safe v1 -> v2 migration: read legacy data only when v2 is absent/corrupt.
    // The caller compares this legacy timestamp with the server layout, then
    // saveFurniture() writes the selected winner to v2. v1 is deliberately kept
    // for a compatibility window instead of being deleted during hydration.
    return loadStoredArray(LEGACY_STORAGE_KEY, namespace);
  } catch {
    try {
      return loadStoredArray(LEGACY_STORAGE_KEY, namespace);
    } catch {
      return null;
    }
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

export type ServerLayout = {
  items: FurnitureItem[];
  updatedAt: string | null;
  version: number | null;
};

let lastServerVersion: number | null = null;

export async function fetchServerLayout(): Promise<ServerLayout | null> {
  try {
    const res = await getOfficeLayout();
    lastServerVersion = typeof res.version === "number" ? res.version : null;
    return Array.isArray(res.items) && (res.items.length > 0 || res.updated_at)
      ? {
          items: res.items as FurnitureItem[],
          updatedAt: res.updated_at ?? null,
          version: lastServerVersion,
        }
      : null;
  } catch (e) {
    console.warn("[layout] server fetch failed, using local fallback", e);
    return null;
  }
}

export async function pushServerLayout(items: FurnitureItem[]): Promise<boolean> {
  try {
    const result = await saveOfficeLayout(items, lastServerVersion);
    lastServerVersion = result.version;
    return true;
  } catch (e) {
    console.warn("[layout] server push failed (kept locally only)", e);
    return false;
  }
}
