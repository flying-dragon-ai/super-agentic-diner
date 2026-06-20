// Ported from Claw3D retro-office core/navigation.ts. Self-contained 25px grid
// A* pathfinder with corner-clipping correction. Strips gym/qa/janitor extras.
import { CANVAS_H, CANVAS_W } from "./constants";
import { getItemBounds, ITEM_FOOTPRINT, ITEM_METADATA, snap } from "./geometry";
import type { FacingPoint, FurnitureItem } from "./types";

export const ROAM_POINTS = [
  { x: 800, y: 200 },
  { x: 850, y: 500 },
  { x: 820, y: 580 },
  { x: 450, y: 420 },
  { x: 250, y: 420 },
  { x: 650, y: 420 },
  { x: 150, y: 620 },
];

const GRID_CELL = 25;
const GRID_COLS = Math.ceil(CANVAS_W / GRID_CELL);
const GRID_ROWS = Math.ceil(CANVAS_H / GRID_CELL);

export type NavGrid = Uint8Array;

const itemBlocksNavigation = (type: string): boolean =>
  ITEM_METADATA[type]?.blocksNavigation ?? false;

export function buildNavGrid(furniture: FurnitureItem[]): NavGrid {
  const grid = new Uint8Array(GRID_COLS * GRID_ROWS);
  const defaultPad = GRID_CELL * 0.6;
  for (const item of furniture) {
    if (!itemBlocksNavigation(item.type)) continue;
    const itemPad = ITEM_METADATA[item.type]?.navPadding ?? defaultPad;
    const bounds = getItemBounds(item);
    const x1 = bounds.x - itemPad;
    const y1 = bounds.y - itemPad;
    const x2 = bounds.x + bounds.w + itemPad;
    const y2 = bounds.y + bounds.h + itemPad;
    const c1 = Math.max(0, Math.floor(x1 / GRID_CELL));
    const c2 = Math.min(GRID_COLS - 1, Math.floor(x2 / GRID_CELL));
    const r1 = Math.max(0, Math.floor(y1 / GRID_CELL));
    const r2 = Math.min(GRID_ROWS - 1, Math.floor(y2 / GRID_CELL));
    for (let row = r1; row <= r2; row += 1) {
      for (let column = c1; column <= c2; column += 1) {
        grid[row * GRID_COLS + column] = 1;
      }
    }
  }
  // Border walls so agents never leave the floor.
  for (let column = 0; column < GRID_COLS; column += 1) {
    grid[column] = 1;
    grid[(GRID_ROWS - 1) * GRID_COLS + column] = 1;
  }
  for (let row = 0; row < GRID_ROWS; row += 1) {
    grid[row * GRID_COLS] = 1;
    grid[row * GRID_COLS + GRID_COLS - 1] = 1;
  }
  return grid;
}

export function astar(
  sx: number,
  sy: number,
  ex: number,
  ey: number,
  grid: NavGrid,
): { x: number; y: number }[] {
  const clamp = (value: number, low: number, high: number) =>
    Math.min(high, Math.max(low, value));
  const toCell = (x: number, y: number) => ({
    c: clamp(Math.floor(x / GRID_CELL), 0, GRID_COLS - 1),
    r: clamp(Math.floor(y / GRID_CELL), 0, GRID_ROWS - 1),
  });
  const cellCx = (column: number) => column * GRID_CELL + GRID_CELL / 2;
  const cellCy = (row: number) => row * GRID_CELL + GRID_CELL / 2;

  const findFree = (column: number, row: number) => {
    if (!grid[row * GRID_COLS + column]) return { c: column, r: row };
    for (let distance = 1; distance < 10; distance += 1) {
      for (let rowOffset = -distance; rowOffset <= distance; rowOffset += 1) {
        for (let columnOffset = -distance; columnOffset <= distance; columnOffset += 1) {
          if (Math.abs(rowOffset) !== distance && Math.abs(columnOffset) !== distance) continue;
          const nextRow = row + rowOffset;
          const nextColumn = column + columnOffset;
          if (nextRow < 0 || nextRow >= GRID_ROWS || nextColumn < 0 || nextColumn >= GRID_COLS) continue;
          if (!grid[nextRow * GRID_COLS + nextColumn]) return { c: nextColumn, r: nextRow };
        }
      }
    }
    return null;
  };

  let { c: sc, r: sr } = toCell(sx, sy);
  let { c: ec, r: er } = toCell(ex, ey);
  const startFree = findFree(sc, sr);
  const endFree = findFree(ec, er);
  if (!startFree || !endFree) return [];
  sc = startFree.c;
  sr = startFree.r;
  ec = endFree.c;
  er = endFree.r;
  if (sc === ec && sr === er) return [{ x: ex, y: ey }];

  const nodeCount = GRID_COLS * GRID_ROWS;
  const gCost = new Float32Array(nodeCount).fill(Infinity);
  const parent = new Int32Array(nodeCount).fill(-1);
  const visited = new Uint8Array(nodeCount);
  const startIndex = sr * GRID_COLS + sc;
  const endIndex = er * GRID_COLS + ec;
  gCost[startIndex] = 0;

  const open: [number, number][] = [];
  const pushOpen = (entry: [number, number]) => {
    open.push(entry);
    let index = open.length - 1;
    while (index > 0) {
      const parentIndex = Math.floor((index - 1) / 2);
      if (open[parentIndex][1] <= entry[1]) break;
      open[index] = open[parentIndex];
      index = parentIndex;
    }
    open[index] = entry;
  };
  const popOpen = (): [number, number] | null => {
    if (open.length === 0) return null;
    const first = open[0];
    const last = open.pop();
    if (!last || open.length === 0) return first;
    let index = 0;
    while (true) {
      const leftIndex = index * 2 + 1;
      const rightIndex = leftIndex + 1;
      if (leftIndex >= open.length) break;
      let smallestIndex = leftIndex;
      if (rightIndex < open.length && open[rightIndex][1] < open[leftIndex][1]) smallestIndex = rightIndex;
      if (open[smallestIndex][1] >= last[1]) break;
      open[index] = open[smallestIndex];
      index = smallestIndex;
    }
    open[index] = last;
    return first;
  };
  pushOpen([startIndex, Math.hypot(ec - sc, er - sr)]);
  const directions: [number, number, number][] = [
    [1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1],
    [1, 1, 1.414], [1, -1, 1.414], [-1, 1, 1.414], [-1, -1, 1.414],
  ];

  while (open.length) {
    const next = popOpen();
    if (!next) break;
    const [current] = next;
    if (visited[current]) continue;
    visited[current] = 1;
    if (current === endIndex) {
      const path: { x: number; y: number }[] = [];
      let node = current;
      while (node !== startIndex) {
        path.push({ x: cellCx(node % GRID_COLS), y: cellCy(Math.floor(node / GRID_COLS)) });
        node = parent[node];
      }
      path.reverse();
      if (path.length) path[path.length - 1] = { x: ex, y: ey };
      else path.push({ x: ex, y: ey });
      return path;
    }
    const currentColumn = current % GRID_COLS;
    const currentRow = Math.floor(current / GRID_COLS);
    for (const [columnOffset, rowOffset, cost] of directions) {
      const nextColumn = currentColumn + columnOffset;
      const nextRow = currentRow + rowOffset;
      if (nextColumn < 0 || nextColumn >= GRID_COLS || nextRow < 0 || nextRow >= GRID_ROWS) continue;
      const nextIndex = nextRow * GRID_COLS + nextColumn;
      if (visited[nextIndex] || grid[nextIndex]) continue;
      if (columnOffset !== 0 && rowOffset !== 0) {
        const orthogonalA = (currentRow + rowOffset) * GRID_COLS + currentColumn;
        const orthogonalB = currentRow * GRID_COLS + (currentColumn + columnOffset);
        if (grid[orthogonalA] || grid[orthogonalB]) continue;
      }
      const nextCost = gCost[current] + cost;
      if (nextCost < gCost[nextIndex]) {
        gCost[nextIndex] = nextCost;
        parent[nextIndex] = current;
        pushOpen([nextIndex, nextCost + Math.hypot(ec - nextColumn, er - nextRow)]);
      }
    }
  }
  return [];
}

export const getDeskLocations = (items: FurnitureItem[]) =>
  items
    .filter((item) => item.type === "desk_cubicle")
    .map((item) => ({ x: item.x + 40, y: item.y - 5 }));

export type { FacingPoint };
export const ENTRY_POINT: FacingPoint = { x: 80, y: 360, facing: Math.PI / 2 };
void ITEM_FOOTPRINT;
void snap;
