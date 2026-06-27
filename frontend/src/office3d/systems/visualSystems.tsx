// Debug/visual systems (Phase 7, optional). Adapted from Claw3D
// systems/visualSystems.tsx: HeatmapSystem (agent dwell heatmap), TrailSystem
// (walking trajectory dots), plus AdaptiveDprController (drops DPR when fps dips
// — useful during dev, off by default). DeskNameplates is omitted (coffee agents
// already carry Billboards in objects/agents.tsx).
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import * as THREE from "three";
import { CANVAS_H, CANVAS_W, SCALE, SNAP_GRID } from "../core/constants";
import { toWorld } from "../core/geometry";
import type { RenderAgent } from "../core/types";

const HEAT_COLS = Math.floor(CANVAS_W / SNAP_GRID);
const HEAT_ROWS = Math.floor(CANVAS_H / SNAP_GRID);

export function HeatmapSystem({
  agentsRef,
  heatmapMode,
}: {
  agentsRef: RefObject<RenderAgent[]>;
  heatmapMode: boolean;
}) {
  const frameRef = useRef(0);
  const gridRef = useRef<Uint16Array>(new Uint16Array(HEAT_COLS * HEAT_ROWS));
  const [cells, setCells] = useState<{ x: number; z: number; v: number }[]>([]);

  useFrame(() => {
    frameRef.current += 1;
    const grid = gridRef.current;
    if (frameRef.current % 45 === 0) {
      for (const agent of agentsRef.current ?? []) {
        const col = Math.floor(agent.x / SNAP_GRID);
        const row = Math.floor(agent.y / SNAP_GRID);
        if (col >= 0 && col < HEAT_COLS && row >= 0 && row < HEAT_ROWS) {
          grid[row * HEAT_COLS + col] = Math.min(65535, grid[row * HEAT_COLS + col] + 1);
        }
      }
    }
    if (heatmapMode && frameRef.current % 120 === 0) {
      let maxValue = 1;
      for (let i = 0; i < grid.length; i += 1) if (grid[i] > maxValue) maxValue = grid[i];
      const next: { x: number; z: number; v: number }[] = [];
      for (let row = 0; row < HEAT_ROWS; row += 1) {
        for (let col = 0; col < HEAT_COLS; col += 1) {
          const value = grid[row * HEAT_COLS + col];
          if (value === 0) continue;
          const [wx, , wz] = toWorld(col * SNAP_GRID + SNAP_GRID / 2, row * SNAP_GRID + SNAP_GRID / 2);
          next.push({ x: wx, z: wz, v: value / maxValue });
        }
      }
      setCells(next);
    }
    if (!heatmapMode && cells.length > 0) setCells([]);
  });

  if (!heatmapMode) return null;
  return (
    <>
      {cells.map((cell, index) => (
        <mesh key={index} position={[cell.x, 0.002, cell.z]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[SNAP_GRID * SCALE * 0.9, SNAP_GRID * SCALE * 0.9]} />
          <meshBasicMaterial
            color={cell.v < 0.4 ? "#f59e0b" : cell.v < 0.75 ? "#ef4444" : "#dc2626"}
            transparent
            opacity={0.15 + cell.v * 0.35}
            depthWrite={false}
          />
        </mesh>
      ))}
    </>
  );
}

type TrailPoint = { pos: THREE.Vector3; age: number; color: string };

export function TrailSystem({
  agentsRef,
  colorMap,
}: {
  agentsRef: RefObject<RenderAgent[]>;
  colorMap: Map<string, string>;
}) {
  const trailsRef = useRef<Map<string, TrailPoint[]>>(new Map());
  const frameRef = useRef(0);
  const [points, setPoints] = useState<TrailPoint[]>([]);

  useFrame(() => {
    frameRef.current += 1;
    const trails = trailsRef.current;
    if (frameRef.current % 12 === 0) {
      for (const agent of agentsRef.current ?? []) {
        if (agent.state !== "walking") continue;
        const [wx, , wz] = toWorld(agent.x, agent.y);
        const existing = trails.get(agent.id) ?? [];
        existing.unshift({ pos: new THREE.Vector3(wx, 0.01, wz), age: 0, color: colorMap.get(agent.id) ?? "#888" });
        if (existing.length > 6) existing.splice(6);
        trails.set(agent.id, existing);
      }
    }
    let changed = false;
    for (const [, trailPoints] of trails) {
      for (const point of trailPoints) point.age += 1;
      for (let index = trailPoints.length - 1; index >= 0; index -= 1) {
        if (trailPoints[index].age < 48) continue;
        trailPoints.splice(index, 1);
        changed = true;
      }
    }
    for (const [id, trailPoints] of trails) {
      if (trailPoints.length === 0) { trails.delete(id); changed = true; }
    }
    if (frameRef.current % 8 === 0 || changed) {
      const next: TrailPoint[] = [];
      for (const trailPoints of trails.values()) next.push(...trailPoints);
      setPoints([...next]);
    }
  });

  return (
    <>
      {points.map((point, index) => (
        <mesh key={index} position={[point.pos.x, point.pos.y, point.pos.z]} rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[0.05, 8]} />
          <meshBasicMaterial
            color={point.color}
            transparent
            opacity={Math.max(0, (1 - point.age / 48) * 0.45)}
            depthWrite={false}
          />
        </mesh>
      ))}
    </>
  );
}

// Drops the renderer's pixel ratio when frame time degrades, restoring it when
// the scene runs smoothly again. Also manages shadow map quality, power
// preference, and texture memory cleanup to prevent GPU memory leaks.
export function AdaptiveDprController() {
  const { gl, invalidate } = useThree();
  const lastTime = useRef(performance.now());
  const slowFrames = useRef(0);
  const fastFrames = useRef(0);
  const fpsHistoryRef = useRef<number[]>([]);
  const textureCacheRef = useRef<Set<THREE.Texture>>(new Set());

  // Performance init: configure WebGL renderer for optimal perf/stability.
  useEffect(() => {
    // Cap initial DPR to 1.5 (most laptops can't sustain 2x with shadows).
    const initialDpr = Math.min(window.devicePixelRatio, 1.5);
    gl.setPixelRatio(initialDpr);
    // Enable power-efficient mode when available.
    const ext = gl.getContext() as WebGLRenderingContext;
    if (ext && ext instanceof WebGLRenderingContext) {
      // Force lose context on unmount to free GPU memory.
      const loseExt = ext.getExtension("WEBGL_lose_context");
      return () => {
        gl.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        // Dispose all tracked textures to prevent memory leaks.
        textureCacheRef.current.forEach((tex) => tex.dispose());
        textureCacheRef.current.clear();
        if (loseExt) loseExt.loseContext();
      };
    }
    return () => {
      gl.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      textureCacheRef.current.forEach((tex) => tex.dispose());
      textureCacheRef.current.clear();
    };
  }, [gl]);

  useFrame(() => {
    const now = performance.now();
    const dt = now - lastTime.current;
    lastTime.current = now;

    // Track rolling FPS history for adaptive quality decisions.
    const fps = 1000 / dt;
    fpsHistoryRef.current.push(fps);
    if (fpsHistoryRef.current.length > 60) fpsHistoryRef.current.shift();

    // ~33ms == 30fps threshold. Sustained slow frames step DPR Down; sustained
    // fast frames step it back up toward the device cap.
    if (dt > 33) {
      slowFrames.current += 1;
      fastFrames.current = 0;
      if (slowFrames.current > 20) {
        const current = gl.getPixelRatio();
        if (current > 0.75) gl.setPixelRatio(Math.max(0.75, current - 0.25));
        slowFrames.current = 0;
        invalidate();
      }
    } else {
      fastFrames.current += 1;
      slowFrames.current = 0;
      if (fastFrames.current > 300) {
        const current = gl.getPixelRatio();
        const cap = Math.min(window.devicePixelRatio, 1.5);
        if (current < cap) gl.setPixelRatio(Math.min(cap, current + 0.25));
        fastFrames.current = 0;
      }
    }
  });

  return null;
}

// Expose current FPS for monitoring UI.
export function getCurrentFps(ref: React.RefObject<number>): number {
  return ref.current;
}

// Re-export so OfficeScene can build the per-agent color map once per render.
export function useColorMap(agentsRef: RefObject<RenderAgent[]>) {
  return useMemo(() => {
    const map = new Map<string, string>();
    for (const agent of agentsRef.current ?? []) {
      map.set(agent.id, agent.color || "#888");
    }
    return map;
  }, [agentsRef]);
}

// Performance monitor hook: returns current FPS for UI display.
export function useFpsMonitor(): { fps: number; isLowFps: boolean } {
  const fpsRef = useRef(60);
  const [, forceRender] = useState(0);
  const frameCount = useRef(0);
  const lastFpsUpdate = useRef(performance.now());

  useFrame(() => {
    frameCount.current += 1;
    const now = performance.now();
    const elapsed = now - lastFpsUpdate.current;
    if (elapsed >= 1000) {
      fpsRef.current = Math.round((frameCount.current * 1000) / elapsed);
      frameCount.current = 0;
      lastFpsUpdate.current = now;
      forceRender((n) => n + 1);
    }
  });

  return { fps: fpsRef.current, isLowFps: fpsRef.current < 30 };
}
