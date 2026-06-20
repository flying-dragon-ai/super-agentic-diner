// Ported from Claw3D retro-office core/geometry.ts. Self-contained math for
// canvas->world projection, furniture footprints/bounds, nav-blocking metadata.
import {
  CANVAS_H,
  CANVAS_W,
  DOOR_LENGTH,
  DOOR_THICKNESS,
  MIN_WALL_LENGTH,
  SCALE,
  SNAP_GRID,
  WALL_THICKNESS,
} from "./constants";
import type { CanvasPoint, FurnitureItem } from "./types";

export const toWorld = (cx: number, cy: number): [number, number, number] => [
  cx * SCALE - CANVAS_W * SCALE * 0.5,
  0,
  cy * SCALE - CANVAS_H * SCALE * 0.5,
];

export const snap = (value: number) => Math.round(value / SNAP_GRID) * SNAP_GRID;

let uidCounter = 0;
export const nextUid = () => `fi_${Date.now()}_${uidCounter++}`;

export const normalizeDegrees = (value: number) => {
  const normalized = value % 360;
  return normalized < 0 ? normalized + 360 : normalized;
};

export const resolveItemTypeKey = (item: FurnitureItem) =>
  item.type === "couch" && item.vertical ? "couch_v" : item.type;

export const ITEM_FOOTPRINT: Record<string, [number, number]> = {
  wall: [80, WALL_THICKNESS],
  door: [DOOR_LENGTH, DOOR_THICKNESS],
  desk_cubicle: [100, 55],
  chair: [24, 24],
  round_table: [120, 120],
  executive_desk: [130, 65],
  couch: [100, 40],
  couch_v: [40, 80],
  bookshelf: [80, 120],
  plant: [24, 24],
  beanbag: [40, 40],
  table_rect: [80, 40],
  coffee_machine: [32, 34],
  coffee_machine_compact: [30, 28],
  coffee_machine_grinder: [34, 32],
  fridge: [40, 80],
  water_cooler: [20, 54],
  atm: [42, 38],
  vending: [40, 60],
  jukebox: [60, 40],
  stove: [40, 40],
  microwave: [30, 20],
  wall_cabinet: [80, 20],
  sink: [40, 40],
  dishwasher: [60, 40],
  pingpong: [100, 60],
  whiteboard: [10, 60],
  cabinet: [200, 40],
  computer: [30, 20],
  lamp: [30, 30],
  printer: [40, 35],
  kanban_board: [130, 65],
  keyboard: [30, 14],
  mouse: [16, 10],
  trash: [20, 20],
  mug: [14, 14],
  clock: [20, 20],
  coffee_cup: [10, 10],
  espresso: [12, 12],
};

export const getItemBaseSize = (item: FurnitureItem) => {
  if (item.r !== undefined) return { width: item.r * 2, height: item.r * 2 };
  const [defaultWidth, defaultHeight] =
    ITEM_FOOTPRINT[resolveItemTypeKey(item)] ?? [item.w ?? 40, item.h ?? 40];
  return { width: item.w ?? defaultWidth, height: item.h ?? defaultHeight };
};

export const ITEM_METADATA: Record<
  string,
  { blocksNavigation: boolean; navPadding?: number }
> = {
  // structural
  wall: { blocksNavigation: true },
  door: { blocksNavigation: false },
  // seating / lounge
  chair: { blocksNavigation: false },
  couch: { blocksNavigation: true },
  couch_v: { blocksNavigation: true },
  beanbag: { blocksNavigation: true },
  // desks / workstations
  desk_cubicle: { blocksNavigation: true, navPadding: 0 },
  executive_desk: { blocksNavigation: true },
  kanban_board: { blocksNavigation: true },
  // tables
  round_table: { blocksNavigation: true },
  table_rect: { blocksNavigation: true },
  pingpong: { blocksNavigation: true },
  // storage / shelving
  bookshelf: { blocksNavigation: true },
  cabinet: { blocksNavigation: true },
  wall_cabinet: { blocksNavigation: false },
  // kitchen appliances (bar back-counter)
  fridge: { blocksNavigation: true },
  stove: { blocksNavigation: true },
  microwave: { blocksNavigation: false },
  dishwasher: { blocksNavigation: true },
  sink: { blocksNavigation: true },
  coffee_machine: { blocksNavigation: false },
  coffee_machine_compact: { blocksNavigation: false },
  coffee_machine_grinder: { blocksNavigation: false },
  vending: { blocksNavigation: true },
  // cafe machines
  atm: { blocksNavigation: true },
  jukebox: { blocksNavigation: true },
  // office equipment / props
  printer: { blocksNavigation: true },
  computer: { blocksNavigation: false },
  keyboard: { blocksNavigation: false },
  mouse: { blocksNavigation: false },
  water_cooler: { blocksNavigation: true },
  whiteboard: { blocksNavigation: true },
  plant: { blocksNavigation: true },
  lamp: { blocksNavigation: false },
  trash: { blocksNavigation: false },
  clock: { blocksNavigation: false },
  mug: { blocksNavigation: false },
  coffee_cup: { blocksNavigation: false },
  espresso: { blocksNavigation: false },
};

export const FURNITURE_ROTATION: Record<string, number> = {
  couch: Math.PI,
  couch_v: Math.PI / 2,
  executive_desk: -Math.PI / 2,
  whiteboard: Math.PI / 2,
};

export const getItemRotationRadians = (item: FurnitureItem) =>
  ((item.facing ?? 0) * Math.PI) / 180 +
  (FURNITURE_ROTATION[resolveItemTypeKey(item)] ?? 0);

export const getItemBounds = (item: FurnitureItem) => {
  const { width, height } = getItemBaseSize(item);
  const rotation = getItemRotationRadians(item);
  const absCos = Math.abs(Math.cos(rotation));
  const absSin = Math.abs(Math.sin(rotation));
  const boundsWidth = width * absCos + height * absSin;
  const boundsHeight = width * absSin + height * absCos;
  const centerX = item.x + width / 2;
  const centerY = item.y + height / 2;
  return {
    x: centerX - boundsWidth / 2,
    y: centerY - boundsHeight / 2,
    w: boundsWidth,
    h: boundsHeight,
    width,
    height,
  };
};

export const createWallItem = (
  start: CanvasPoint,
  end: CanvasPoint,
  uid: string,
): FurnitureItem => {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const horizontal = Math.abs(dx) >= Math.abs(dy);
  if (horizontal) {
    const minX = Math.min(start.x, end.x);
    const maxX = Math.max(start.x, end.x);
    return {
      _uid: uid,
      type: "wall",
      x: snap(minX),
      y: snap(start.y) - WALL_THICKNESS / 2,
      w: Math.max(MIN_WALL_LENGTH, snap(maxX - minX) + WALL_THICKNESS),
      h: WALL_THICKNESS,
      facing: 0,
    };
  }
  const minY = Math.min(start.y, end.y);
  const maxY = Math.max(start.y, end.y);
  return {
    _uid: uid,
    type: "wall",
    x: snap(start.x) - WALL_THICKNESS / 2,
    y: snap(minY),
    w: WALL_THICKNESS,
    h: Math.max(MIN_WALL_LENGTH, snap(maxY - minY) + WALL_THICKNESS),
    facing: 0,
  };
};
