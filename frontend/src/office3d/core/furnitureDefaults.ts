// Coffee shop scene layout for the 3D floor. DEFAULT_FURNITURE arranges a bar
// (left), a 2x2 round-table seating block (center), a sofa lounge (right), and
// wall props/decor across a 1800x720 canvas. materializeDefaults turns the
// FurnitureSeed[] into FurnitureItem[] with stable _uids for OfficeScene.
import type { FurnitureItem, FurnitureSeed } from "./types";

export const DEFAULT_FURNITURE: FurnitureSeed[] = [
  // --- Bar area (left, x:0-480): L-shaped counter, back-bar, register, stools ---
  { type: "cabinet", x: 60, y: 30, w: 280, h: 40 },
  { type: "fridge", x: 360, y: 30, w: 40, h: 80 },
  { type: "executive_desk", x: 100, y: 135 },
  { type: "coffee_machine", x: 130, y: 150, elevation: 0.56 },
  { type: "computer", x: 185, y: 150 },
  { type: "chair", x: 120, y: 215, facing: 180 },
  { type: "chair", x: 165, y: 215, facing: 180 },
  { type: "chair", x: 210, y: 215, facing: 180 },
  { type: "plant", x: 30, y: 330 },
  { type: "trash", x: 300, y: 210 },
  { type: "espresso", x: 155, y: 142, elevation: 0.69 },
  { type: "coffee_cup", x: 205, y: 142, elevation: 0.88 },

  // --- Seating area (center, x:480-1180): 4 round-table groups in a 2x2 grid ---
  // Group 1 (table center 620,230)
  { type: "round_table", x: 565, y: 165, r: 55 },
  { type: "chair", x: 608, y: 158, facing: 0 },
  { type: "chair", x: 608, y: 290, facing: 180 },
  { type: "chair", x: 548, y: 218, facing: 90 },
  { type: "chair", x: 680, y: 218, facing: 270 },
  // Group 2 (table center 1000,230)
  { type: "round_table", x: 945, y: 165, r: 55 },
  { type: "chair", x: 988, y: 158, facing: 0 },
  { type: "chair", x: 988, y: 290, facing: 180 },
  { type: "chair", x: 928, y: 218, facing: 90 },
  { type: "chair", x: 1060, y: 218, facing: 270 },
  // Group 3 (table center 620,480)
  { type: "round_table", x: 565, y: 425, r: 55 },
  { type: "chair", x: 608, y: 408, facing: 0 },
  { type: "chair", x: 608, y: 540, facing: 180 },
  { type: "chair", x: 548, y: 468, facing: 90 },
  { type: "chair", x: 680, y: 468, facing: 270 },
  // Group 4 (table center 1000,480)
  { type: "round_table", x: 945, y: 425, r: 55 },
  { type: "chair", x: 988, y: 408, facing: 0 },
  { type: "chair", x: 988, y: 540, facing: 180 },
  { type: "chair", x: 928, y: 468, facing: 90 },
  { type: "chair", x: 1060, y: 468, facing: 270 },
  // coffee cups centered on each round table (table center coords)
  { type: "coffee_cup", x: 615, y: 215, elevation: 0.5 },
  { type: "coffee_cup", x: 995, y: 215, elevation: 0.5 },
  { type: "coffee_cup", x: 615, y: 475, elevation: 0.5 },
  { type: "coffee_cup", x: 995, y: 475, elevation: 0.5 },

  // --- Lounge sofa area (right, x:1200-1750) ---
  { type: "couch", x: 1280, y: 150, w: 120, h: 45 },
  { type: "table_rect", x: 1300, y: 215, w: 80, h: 40 },
  { type: "beanbag", x: 1430, y: 150, color: "#c0392b" },
  { type: "beanbag", x: 1500, y: 150, color: "#1565c0" },
  { type: "couch_v", x: 1280, y: 280 },
  { type: "round_table", x: 1530, y: 300, r: 40 },
  { type: "chair", x: 1558, y: 280, facing: 0 },
  { type: "chair", x: 1558, y: 388, facing: 180 },

  // --- Wall props + decor ---
  // --- Cafe machines (Phase 5a): self-checkout, vending, jukebox ---
  // --- Cafe entrance door (west edge, auto-opens when agents approach) ---
  { type: "door", x: 30, y: 330, facing: 0 },
  // --- Cafe machines (Phase 5a): self-checkout, vending, jukebox ---
  { type: "atm", x: 410, y: 220 },
  { type: "vending", x: 430, y: 600 },
  { type: "jukebox", x: 1620, y: 600 },
  // --- Wall props + decor ---
  { type: "whiteboard", x: 700, y: 15, w: 12, h: 70, color: "#3e2723" },
  { type: "whiteboard", x: 1080, y: 15, w: 12, h: 70, color: "#3e2723" },
  { type: "whiteboard", x: 1620, y: 15, w: 12, h: 70, color: "#5d4037" },
  { type: "bookshelf", x: 1150, y: 25, w: 80, h: 120 },
  { type: "clock", x: 480, y: 12 },
  { type: "lamp", x: 460, y: 600 },
  { type: "lamp", x: 1180, y: 600 },
  { type: "lamp", x: 1700, y: 400 },
  { type: "plant", x: 30, y: 660 },
  { type: "plant", x: 470, y: 660 },
  { type: "plant", x: 1140, y: 660 },
  { type: "plant", x: 1700, y: 60 },
  { type: "plant", x: 1700, y: 660 },
  { type: "plant", x: 470, y: 120 },
  { type: "trash", x: 1080, y: 560 },
  { type: "trash", x: 1340, y: 400 },
];

import {
  loadFurniture,
  hasLayoutMigrationApplied,
  markLayoutMigrationApplied,
} from "./persistence";

// Stable per-item signature for smooth layout migration (ported concept from
// Claw3D createFurnitureSignature). Two layouts share an item iff every field
// below matches, so the editor can detect "is this the old default layout?" and
// replace only the matching items when the default layout is upgraded.
export const createFurnitureSignature = (item: FurnitureSeed | FurnitureItem) =>
  [
    item.type,
    item.x,
    item.y,
    item.w ?? "",
    item.h ?? "",
    item.r ?? "",
    item.facing ?? "",
    item.vertical ? 1 : 0,
    item.elevation ?? "",
  ].join(":");

// Signature of the *current* default layout. Bumping the layout (adding/moving
// default items) changes this set, letting the editor decide whether a saved
// editor layout still represents the old default and should be refreshed.
export const DEFAULT_LAYOUT_SIGNATURES = new Set(
  DEFAULT_FURNITURE.map(createFurnitureSignature),
);

export const hasAllDefaultSignatures = (items: FurnitureItem[]) => {
  if (items.length < DEFAULT_LAYOUT_SIGNATURES.size) return false;
  const itemSignatures = new Set(items.map(createFurnitureSignature));
  return [...DEFAULT_LAYOUT_SIGNATURES].every((signature) =>
    itemSignatures.has(signature),
  );
};

// Resolve the effective furniture layout. The very first load seeds the
// migration flag and returns the default; later loads reuse a saved editor
// layout if present so user edits survive reloads.
export const resolveFurnitureLayout = (
  namespace = "default",
): FurnitureItem[] => {
  if (!hasLayoutMigrationApplied(namespace)) {
    markLayoutMigrationApplied(namespace);
    return materializeDefaults();
  }
  return loadFurniture(namespace) ?? materializeDefaults();
};

export const materializeDefaults = (): FurnitureItem[] =>
  DEFAULT_FURNITURE.map((item, index) => ({ ...item, _uid: `office_${index}` }));
