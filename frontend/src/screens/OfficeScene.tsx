// 3D office scene. Renders the cafe layout with real GLB furniture models, the
// overview 3/4 camera, and agents driven by /ws/visualization events through the
// sim store + tick. Phase 4 adds a coffee-shop furniture editor (palette / drag /
// select / keyboard / wall draw) layered on OrbitControls via the FloorRaycaster.
// Phase 5 wires procedural cafe machines + an immersive overlay.
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FloorAndWalls } from "../office3d/scene/environment";
import { MenuBoardArt, CafePendantLights } from "../office3d/scene/environment";
import {
  SceneLighting,
  OVERVIEW_CAMERA,
  OVERVIEW_TARGET,
  OVERVIEW_ZOOM,
  CAMERA_PRESETS,
  CameraAnimator,
  FollowCamController,
  type CameraPreset,
} from "../office3d/systems/cameraLighting";
import {
  GameLoop,
  SpotlightEffect,
  FloorRaycaster,
} from "../office3d/systems/sceneRuntime";
import { AgentModel } from "../office3d/objects/agents";
import { FurnitureModel, PlacementGhost } from "../office3d/objects/furniture";
import { resolveMachine } from "../office3d/objects/machines";
import { DoorModel } from "../office3d/objects/primitives";
import {
  CANVAS_W,
  CANVAS_H,
  ELEVATION_STEP,
  ROTATION_STEP_DEG,
  SCALE,
  SNAP_GRID,
} from "../office3d/core/constants";
import {
  materializeDefaults,
  resolveFurnitureLayout,
} from "../office3d/core/furnitureDefaults";
import { saveFurniture } from "../office3d/core/persistence";
import { createWallItem, nextUid, snap } from "../office3d/core/geometry";
import type { FurnitureItem, RenderAgent } from "../office3d/core/types";
import { createSimStore, applyEvent, clearSpeech } from "../sim/agentStore";
import { makeTick } from "../sim/tick";
import { connectVisualization } from "../net/visualizationSocket";
import type { SnapshotAgent, VisEvent } from "../net/api";
import { ROLE_LABEL, resolveAction, resolveRole } from "../sim/roleMap";
import { Palette, PALETTE } from "../ui/Palette";
import { ImmersiveOverlay, type OverlayKind } from "../overlays/ImmersiveOverlay";
import {
  HeatmapSystem,
  TrailSystem,
  AdaptiveDprController,
  useColorMap,
} from "../office3d/systems/visualSystems";

const DEFAULT_FURNITURE: FurnitureItem[] = materializeDefaults();

type DragState =
  | { kind: "idle" }
  | { kind: "placing"; itemType: string }
  | { kind: "moving"; uid: string };

export default function OfficeScene() {
  const sim = useMemo(() => createSimStore(), []);
  const agentsRef = useRef<RenderAgent[]>([]);
  const lookupRef = useRef<Map<string, RenderAgent>>(new Map());
  const [tick, setTick] = useState<() => void>(() => () => {});
  const [status, setStatus] = useState("connecting");
  const [events, setEvents] = useState<VisEvent[]>([]);
  const [focusId, setFocusId] = useState<string | null>(null);
  const orbitRef = useRef<OrbitControlsImpl | null>(null);
  const presetRef = useRef<CameraPreset | null>(null);
  const followRef = useRef<string | null>(null);
  const [view, setView] = useState<keyof typeof CAMERA_PRESETS>("overview");

  const [editMode, setEditMode] = useState(false);
  const [furniture, setFurniture] = useState<FurnitureItem[]>(() =>
    resolveFurnitureLayout(),
  );
  const [drag, setDrag] = useState<DragState>({ kind: "idle" });
  const [selectedUid, setSelectedUid] = useState<string | null>(null);
  const [hoverUid, setHoverUid] = useState<string | null>(null);
  const [ghostPos, setGhostPos] = useState<[number, number, number] | null>(null);
  const [wallDrawStart, setWallDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [overlay, setOverlay] = useState<OverlayKind>(null);
  // Phase 7 optional debug overlays + perf safety net.
  const [debug, setDebug] = useState(false);
  const colorMap = useColorMap(agentsRef);

  useEffect(() => {
    sim.setFurniture(furniture);
  }, [sim, furniture]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      saveFurniture(furniture);
    }, 300);
    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [furniture]);

  useEffect(() => { setTick(() => makeTick(sim)); }, [sim]);

  useEffect(() => {
    const socket = connectVisualization({
      onEvent: (event) => {
        setEvents((prev) => [event, ...prev].slice(0, 40));
        // Read-only adapter: backend emits snake_case payloads (display_name /
        // role_type / sprite_seed) wrapped in agent.action/agent.registered;
        // tolerate camelCase too without changing the wire contract.
        const payload = event.payload ?? {};
        const role = resolveRole(
          (payload.role_type as string) ?? (payload.role as string) ?? "customer",
        );
        const meta = {
          id: `agent_${event.agent_id ?? "anon"}`,
          name:
            (payload.display_name as string) ??
            (payload.name as string) ??
            `?? ${event.agent_id ?? "?"}`,
          subtitle: null as string | null,
          role,
          color: (payload.color as string) || "",
          spriteSeed: Number(
            payload.sprite_seed ??
              payload.spriteSeed ??
              (Math.abs((event.agent_id ?? 1) * 7) % 900000) + 100000,
          ),
        };
        // Map the backend event envelope to a sim action.
        // - agent.action: the real action lives in payload.action_type.
        // - agent.registered: a new agent entered -> seat them at their role desk.
        let action = event.type;
        if (event.type === "agent.action") {
          action = (payload.action_type as string) ?? event.type;
        } else if (event.type === "agent.registered") {
          action = "enter_scene";
        }
        applyEvent(sim, meta, action, payload);
        if (resolveAction(action) === "show_message") {
          setTimeout(() => clearSpeech(sim, meta.id), 6000);
        }
      },
      onSnapshot: (agents) => {
        // Pre-create agents from scene.snapshot so late-connecting clients see
        // the fixed staff team + active customers immediately.
        for (const a of agents as SnapshotAgent[]) {
          const meta = {
            id: `agent_${a.agent_id}`,
            name: a.display_name || `?? ${a.agent_id}`,
            subtitle: null as string | null,
            role: resolveRole(a.role_type || "customer"),
            color: "",
            spriteSeed: Number(a.sprite_seed ?? 100000),
          };
          applyEvent(sim, meta, "enter_scene", {});
        }
      },
    });
    return () => socket.close();
  }, [sim]);

  agentsRef.current = sim.agents;
  lookupRef.current = new Map(sim.agents.map((a) => [a.id, a]));

  const [camX, camY, camZ] = OVERVIEW_CAMERA;
  const floorW = CANVAS_W * SCALE;
  const floorH = CANVAS_H * SCALE;

  const worldToCanvas = useCallback((wx: number, wz: number) => ({
    cx: snap(Math.round((wx + CANVAS_W * SCALE * 0.5) / SCALE)),
    cy: snap(Math.round((wz + CANVAS_H * SCALE * 0.5) / SCALE)),
  }), []);

  const switchView = useCallback((key: keyof typeof CAMERA_PRESETS) => {
    setView(key);
    followRef.current = null;
    setFocusId(null);
    presetRef.current = CAMERA_PRESETS[key];
  }, []);

  const focusAgent = useCallback((agentId: string) => {
    setFocusId((prev) => {
      const next = prev === agentId ? null : agentId;
      followRef.current = next;
      return next;
    });
  }, []);

  const startPlacing = useCallback((type: string) => {
    setEditMode(true);
    setDrag({ kind: "placing", itemType: type });
    setSelectedUid(null);
    setWallDrawStart(null);
    setGhostPos(null);
  }, []);

  const toggleEdit = useCallback(() => {
    setEditMode((prev) => {
      const next = !prev;
      if (!next) {
        setDrag({ kind: "idle" });
        setSelectedUid(null);
        setGhostPos(null);
        setWallDrawStart(null);
      }
      return next;
    });
  }, []);

  const handleFloorMove = useCallback((wx: number, wz: number) => {
    setDrag((d) => {
      if (d.kind === "placing") setGhostPos([wx, 0, wz]);
      if (d.kind === "moving") {
        const { cx, cy } = worldToCanvas(wx, wz);
        setFurniture((prev) =>
          prev.map((item) => (item._uid === d.uid ? { ...item, x: cx, y: cy } : item)),
        );
      }
      return d;
    });
  }, [worldToCanvas]);

  const handleFloorClick = useCallback((wx: number, wz: number) => {
    setDrag((d) => {
      if (d.kind === "placing") {
        const { cx, cy } = worldToCanvas(wx, wz);
        if (d.itemType === "wall") {
          if (!wallDrawStart) {
            setWallDrawStart({ x: cx, y: cy });
            setGhostPos([wx, 0, wz]);
            return d;
          }
          const newWall = createWallItem(wallDrawStart, { x: cx, y: cy }, nextUid());
          setFurniture((prev) => [...prev, newWall]);
          setSelectedUid(newWall._uid);
          setDrag({ kind: "idle" });
          setGhostPos(null);
          setWallDrawStart(null);
          return { kind: "idle" };
        }
        const palEntry = PALETTE.find((p) => p.type === d.itemType);
        const isCouch = d.itemType === "couch_v";
        const newItem: FurnitureItem = {
          _uid: nextUid(),
          type: isCouch ? "couch" : d.itemType,
          x: cx,
          y: cy,
          ...(palEntry?.defaults as Partial<FurnitureItem>),
          ...(isCouch ? { vertical: true, w: 40, h: 80 } : {}),
        };
        setFurniture((prev) => [...prev, newItem]);
        setSelectedUid(newItem._uid);
        setDrag({ kind: "idle" });
        setGhostPos(null);
        setWallDrawStart(null);
        return { kind: "idle" };
      }
      if (d.kind === "moving") {
        return { kind: "idle" };
      }
      return d;
    });
  }, [wallDrawStart, worldToCanvas]);

  const handleFurniturePointerDown = useCallback((uid: string) => {
    if (!editMode) return;
    setSelectedUid(uid);
    setDrag({ kind: "moving", uid });
  }, [editMode]);

  // Outside edit mode, clicking a cafe machine opens its immersive panel.
  const handleMachineActivate = useCallback((item: FurnitureItem) => {
    if (editMode) return;
    if (item.type === "atm") setOverlay("order");
    else if (item.type === "coffee_machine") setOverlay("brewing");
  }, [editMode]);

  useEffect(() => {
    if (!editMode) return;
    const onKey = (e: KeyboardEvent) => {
      if (!selectedUid) {
        if (e.key === "Escape") { setDrag({ kind: "idle" }); setGhostPos(null); setWallDrawStart(null); }
        return;
      }
      const step = e.shiftKey ? SNAP_GRID * 5 : SNAP_GRID;
      const move = (dx: number, dy: number) => setFurniture((prev) => prev.map((it) => it._uid === selectedUid ? { ...it, x: Math.max(0, Math.min(CANVAS_W, it.x + dx)), y: Math.max(0, Math.min(CANVAS_H, it.y + dy)) } : it));
      const elevate = (dir: number) => setFurniture((prev) => prev.map((it) => it._uid === selectedUid ? { ...it, elevation: Math.max(0, (it.elevation ?? 0) + dir * ELEVATION_STEP) } : it));
      switch (e.key) {
        case "ArrowLeft": move(-step, 0); break;
        case "ArrowRight": move(step, 0); break;
        case "ArrowUp": move(0, -step); break;
        case "ArrowDown": move(0, step); break;
        case "PageUp": elevate(1); break;
        case "PageDown": elevate(-1); break;
        case "[": case "]":
          setFurniture((prev) => prev.map((it) => it._uid === selectedUid ? { ...it, facing: ((it.facing ?? 0) + (e.key === "[" ? -ROTATION_STEP_DEG : ROTATION_STEP_DEG)) } : it));
          break;
        case "Delete": case "Backspace":
          setFurniture((prev) => prev.filter((it) => it._uid !== selectedUid));
          setSelectedUid(null);
          break;
        case "Escape": setSelectedUid(null); setDrag({ kind: "idle" }); setGhostPos(null); setWallDrawStart(null); break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editMode, selectedUid]);

  const ghostItem = useMemo(() => {
    if (drag.kind !== "placing" || !ghostPos) return null;
    if (drag.itemType === "wall") {
      const { cx, cy } = worldToCanvas(ghostPos[0], ghostPos[2]);
      const start = wallDrawStart ?? { x: cx, y: cy };
      return createWallItem(start, { x: cx, y: cy }, "__wall_ghost__");
    }
    return null;
  }, [drag, ghostPos, wallDrawStart, worldToCanvas]);

  return (
    <div style={{ position: "relative", width: "100vw", height: "100vh", background: "#0b0f14" }}>
      <Canvas
        shadows
        camera={{ position: [camX, camY, camZ], fov: OVERVIEW_ZOOM, near: 0.1, far: 200 }}
        onCreated={({ camera }) => camera.lookAt(OVERVIEW_TARGET[0], OVERVIEW_TARGET[1], OVERVIEW_TARGET[2])}
      >
        <Suspense fallback={null}>
          <SceneLighting />
          <FloorAndWalls />
          <CafePendantLights />
          <MenuBoardArt position={[0, 1.6, -6.3]} />
          {furniture.map((item) => {
            if (item.type === "door") {
              return <DoorModel key={item._uid} item={item} agentsRef={agentsRef} />;
            }
            const Machine = resolveMachine(item);
            if (Machine) {
              return (
                <Machine
                  key={item._uid}
                  item={item}
                  isSelected={selectedUid === item._uid}
                  isHovered={hoverUid === item._uid}
                  onClick={() => handleMachineActivate(item)}
                />
              );
            }
            return (
              <FurnitureModel
                key={item._uid}
                item={item}
                editMode={editMode}
                isSelected={selectedUid === item._uid}
                isHovered={hoverUid === item._uid}
                onPointerDown={() =>
                  item.type === "coffee_machine" && !editMode
                    ? handleMachineActivate(item)
                    : handleFurniturePointerDown(item._uid)
                }
                onPointerOver={() => editMode && setHoverUid(item._uid)}
                onPointerOut={() => setHoverUid(null)}
              />
            );
          })}
          {ghostItem && <FurnitureModel item={ghostItem} />}
          {drag.kind === "placing" && ghostPos && drag.itemType !== "wall" && (
            <PlacementGhost itemType={drag.itemType} position={ghostPos} />
          )}
          {sim.agents.map((agent) => (
            <AgentModel
              key={agent.id}
              agentId={agent.id}
              name={agent.name}
              subtitle={ROLE_LABEL[agent.role ?? "customer"] ?? null}
              status={agent.status}
              color={agent.color}
              agentsRef={agentsRef}
              agentLookupRef={lookupRef}
              showSpeech={sim.speech.has(agent.id)}
              speechText={sim.speech.get(agent.id) ?? null}
              onClick={() => focusAgent(agent.id)}
            />
          ))}
          <SpotlightEffect agentId={focusId} agentsRef={agentsRef} agentLookupRef={lookupRef} />
          <FloorRaycaster enabled={editMode} onMove={handleFloorMove} onClick={handleFloorClick} />
          <CameraAnimator presetRef={presetRef} orbitRef={orbitRef} />
          <FollowCamController followRef={followRef} agentsRef={agentsRef} agentLookupRef={lookupRef} />
          <GameLoop tick={tick} />
        </Suspense>
        <OrbitControls
          ref={orbitRef}
          target={[0, 0, 0]}
          minDistance={6}
          maxDistance={Math.max(floorW, floorH) * 1.4}
          maxPolarAngle={Math.PI / 2.1}
        />
      </Canvas>
      <ImmersiveOverlay kind={overlay} onClose={() => setOverlay(null)} />
      <div style={{ position: "absolute", top: 12, left: 12, color: "#e8dfc0", fontFamily: "monospace", fontSize: 12, background: "rgba(0,0,0,0.55)", padding: "6px 10px", borderRadius: 6 }}>
        <div>Coffee AI Boss · 3D 咖啡厅</div>
        <div style={{ opacity: 0.7 }}>WS: {status} · 在场员工 {sim.agents.length} · 焦点 {focusId ?? "无"}</div>
      </div>
      <div style={{ position: "absolute", top: 12, right: 12, display: "flex", gap: 6 }}>
        {(Object.keys(CAMERA_PRESETS) as (keyof typeof CAMERA_PRESETS)[]).map((key) => (
          <button
            key={key}
            onClick={() => switchView(key)}
            style={{
              padding: "6px 12px",
              fontFamily: "monospace",
              fontSize: 12,
              cursor: "pointer",
              border: view === key ? "1px solid #f0c060" : "1px solid rgba(255,255,255,0.15)",
              background: view === key ? "rgba(240,192,96,0.18)" : "rgba(0,0,0,0.55)",
              color: view === key ? "#f0c060" : "#cfe0ff",
              borderRadius: 6,
            }}
          >
            {key === "overview" ? "全景" : key === "machines" ? "机器" : key === "barCounter" ? "吧台" : "休闲"}
          </button>
        ))}
        <button
          onClick={toggleEdit}
          style={{
            marginLeft: 6,
            padding: "6px 12px",
            fontFamily: "monospace",
            fontSize: 12,
            cursor: "pointer",
            border: editMode ? "1px solid #4ade80" : "1px solid rgba(255,255,255,0.15)",
            background: editMode ? "rgba(74,222,128,0.18)" : "rgba(0,0,0,0.55)",
            color: editMode ? "#4ade80" : "#cfe0ff",
            borderRadius: 6,
          }}
        >
          {editMode ? "✏️ 编辑中" : "✏️ 编辑"}
        </button>
      </div>
      {editMode && (
        <Palette activeType={drag.kind === "placing" ? drag.itemType : null} onPick={startPlacing} />
      )}
      {editMode && selectedUid && (
        <div style={{ position: "absolute", bottom: 12, left: 192, color: "#cfe0ff", fontFamily: "monospace", fontSize: 11, background: "rgba(8,12,20,0.85)", padding: "8px 10px", borderRadius: 6, border: "1px solid rgba(255,255,255,0.08)" }}>
          <div style={{ color: "#fbbf24", marginBottom: 4 }}>已选中 · {selectedUid}</div>
          <div>方向键移动 · PgUp/Dn 抬升 · [ ] 旋转 · Delete 删除 · Esc 取消</div>
          <div style={{ marginTop: 4 }}>
            <button
              onClick={() => {
                setFurniture((prev) => prev.filter((it) => it._uid !== selectedUid));
                setSelectedUid(null);
              }}
              style={{ cursor: "pointer", marginRight: 8, padding: "3px 8px", background: "rgba(239,68,68,0.18)", color: "#fca5a5", border: "1px solid rgba(239,68,68,0.4)", borderRadius: 4 }}
            >
              删除
            </button>
            <button
              onClick={() => {
                setFurniture(DEFAULT_FURNITURE);
                setSelectedUid(null);
              }}
              style={{ cursor: "pointer", padding: "3px 8px", background: "rgba(96,165,250,0.18)", color: "#93c5fd", border: "1px solid rgba(96,165,250,0.4)", borderRadius: 4 }}
            >
              恢复默认布局
            </button>
          </div>
        </div>
      )}
      <div style={{ position: "absolute", bottom: 12, right: 12, width: 360, maxHeight: 260, overflowY: "auto", background: "rgba(8,12,20,0.8)", color: "#cfe0ff", fontFamily: "monospace", fontSize: 11, padding: 8, borderRadius: 6 }}>
        {events.map((e) => (
          <div key={String(e.event_id)} style={{ padding: "2px 0", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
            <span style={{ color: "#f0c060" }}>{e.type}</span>{" "}
            <span style={{ opacity: 0.6 }}>{new Date(e.created_at).toLocaleTimeString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
