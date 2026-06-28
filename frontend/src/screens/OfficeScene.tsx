// 3D office scene. Renders the cafe layout with real GLB furniture models, the
// overview 3/4 camera, and agents driven by /ws/visualization events through the
// sim store + tick. Phase 4 adds a coffee-shop furniture editor (palette / drag /
// select / keyboard / wall draw) layered on OrbitControls via the FloorRaycaster.
// Phase 5 wires procedural cafe machines + an immersive overlay.
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Perf } from "r3f-perf";
import { Leva, useControls } from "leva";
import { FloorAndWalls, EvoMapAmbientLayer } from "../office3d/scene/environment";
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
  ensureEvoMapSceneMaterials,
  isDefaultFurnitureLayout,
  materializeDefaults,
  resolveFurnitureLayout,
} from "../office3d/core/furnitureDefaults";
import {
  saveFurniture,
  loadFurniture,
  loadFurnitureSavedAt,
  fetchServerLayout,
  pushServerLayout,
} from "../office3d/core/persistence";
import { createWallItem, nextUid, normalizeDegrees, snap } from "../office3d/core/geometry";
import type { FurnitureItem, RenderAgent } from "../office3d/core/types";
import { createSimStore, applyEvent, clearSpeech } from "../sim/agentStore";
import { makeTick } from "../sim/tick";
import { connectVisualization } from "../net/visualizationSocket";
import type { SnapshotAgent, VisEvent } from "../net/api";
import { ROLE_LABEL, resolveAction, resolveRole } from "../sim/roleMap";
import { Palette, PALETTE } from "../ui/Palette";
import { SelectedObjectPanel } from "../ui/SelectedObjectPanel";
import { ChatPanel } from "../ui/ChatPanel";
import { VisitorSocialPanel } from "../ui/VisitorSocialPanel";
import { TodayTopicsPanel } from "../ui/TodayTopicsPanel";
import { ImmersiveOverlay, type OverlayKind } from "../overlays/ImmersiveOverlay";
import { SceneErrorBoundary } from "../components/SceneErrorBoundary";
import { initSceneMusic, stopSceneMusic } from "../sounds/sceneMusic";
import {
  TrailSystem,
  AdaptiveDprController,
  useColorMap,
} from "../office3d/systems/visualSystems";

const DEFAULT_FURNITURE: FurnitureItem[] = materializeDefaults();
type LayoutSaveStatus = "idle" | "saving" | "saved" | "local-only";
const LAYOUT_SAVE_TEXT: Record<LayoutSaveStatus, string> = {
  idle: "",
  saving: "保存中",
  saved: "已保存",
  "local-only": "仅本地保存",
};

type DragState =
  | { kind: "idle" }
  | { kind: "placing"; itemType: string }
  | { kind: "moving"; uid: string };

const EVENT_TEXT: Record<string, string> = {
  "message.received": "收到顾客消息",
  "order.intent_detected": "已识别点单需求",
  "order.pending_confirmation": "等待顾客确认订单",
  "order.payment_required": "等待顾客确认支付",
  "order.payment_failed": "支付未完成",
  "order.paid": "支付完成，订单已确认",
  "order.failed": "订单处理失败",
  "order.reply": "店长已回复顾客",
  "restaurant.customer_entered": "顾客进入Crossroads Agent Café",
  "restaurant.order_ticketed": "已生成点单小票",
  "restaurant.order_confirming": "正在确认订单内容",
  "restaurant.payment_requested": "已向顾客发起支付",
  "restaurant.payment_processing": "正在处理支付",
  "restaurant.payment_completed": "支付完成，准备制作",
  "restaurant.payment_failed": "支付失败，等待重试",
  "restaurant.preparation_progress": "咖啡正在制作中",
  "restaurant.order_ready": "咖啡已制作完成",
  "restaurant.order_delivered": "咖啡已送达顾客",
  "restaurant.customer_reviewed": "顾客已完成评价",
  "restaurant.customer_left": "顾客离开Crossroads Agent Café",
  "restaurant.order_failed": "订单流程异常",
  "agent.registered": "员工已进入Crossroads Agent Café",
  "agent.autonomous.decision": "数字顾客自主决策",
  "presence.customer_joined": "在线顾客已进入",
  "presence.customer_moved": "在线顾客正在移动",
  "presence.customer_left": "在线顾客已离开",
};

const AGENT_ACTION_TEXT: Record<string, string> = {
  enter_scene: "员工回到岗位",
  walk_to_counter: "服务员前往点单台",
  take_order: "收银员正在接单",
  prepare_coffee: "咖啡师开始制作",
  deliver_order: "服务员正在送餐",
  show_message: "员工正在回复顾客",
  leave_scene: "员工离开Crossroads Agent Café",
};

function formatSceneEvent(event: VisEvent) {
  if (event.type === "agent.action") {
    const actionType = typeof event.payload?.action_type === "string" ? event.payload.action_type : "";
    return AGENT_ACTION_TEXT[actionType] ?? "员工正在处理订单";
  }
  return EVENT_TEXT[event.type] ?? "Crossroads Agent Café状态已更新";
}

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
  const [layoutSaveStatus, setLayoutSaveStatus] = useState<LayoutSaveStatus>("idle");
  const [drag, setDrag] = useState<DragState>({ kind: "idle" });
  const [selectedUid, setSelectedUid] = useState<string | null>(null);
  // B1: synchronous flag — when a furniture/machine is clicked, the R3F event
  // listener (registered first) runs and sets this true; the FloorRaycaster's
  // native DOM click listener (registered later, same click event) reads it to
  // skip the drag reset, otherwise drag never survives as "moving" and the
  // follow-cursor drag is dead.
  const justSelectedRef = useRef(false);
  // Server-layout hydration flag: false until the mount-time GET completes, so
  // the debounced autosave skips the initial render and doesn't race the GET
  // (which could clobber a newer server layout or upload defaults prematurely).
  const hydratedRef = useRef(false);
  const [hoverUid, setHoverUid] = useState<string | null>(null);
  const [ghostPos, setGhostPos] = useState<[number, number, number] | null>(null);
  const [wallDrawStart, setWallDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [overlay, setOverlay] = useState<OverlayKind>(null);
  const colorMap = useColorMap(agentsRef);
  // Visitor chat consumer: forwarded from the WebSocket event handler so
  // VisitorSocialPanel can display real-time messages without its own WS.
  const visitorChatConsumerRef = useRef<((msg: import("../net/api").VisitorChatMessage) => void) | null>(null);
  const registerChatConsumer = useCallback(
    (handler: (msg: import("../net/api").VisitorChatMessage) => void) => {
      visitorChatConsumerRef.current = handler;
    },
    [],
  );
  const [compactChrome, setCompactChrome] = useState(
    () => typeof window !== "undefined" && window.innerWidth < 700,
  );

  useEffect(() => {
    const syncChrome = () => setCompactChrome(window.innerWidth < 700);
    syncChrome();
    window.addEventListener("resize", syncChrome);
    return () => window.removeEventListener("resize", syncChrome);
  }, []);

  useEffect(() => {
    sim.setFurniture(furniture);
  }, [sim, furniture]);

  // Hydrate from server on mount. Server is authoritative + global (staff edits
  // once, every visitor sees it); localStorage is an instant cache + offline
  // fallback. On first-ever load (server empty) we migrate the current layout
  // (localStorage cache or default) up so the whole project shares one layout.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const server = await fetchServerLayout();
      if (cancelled) return;
      if (server && server.items.length > 0) {
        const serverLayout = ensureEvoMapSceneMaterials(server.items);
        const local = loadFurniture();
        const localLayout = local && local.length > 0 ? ensureEvoMapSceneMaterials(local) : null;
        const localSavedAt = loadFurnitureSavedAt();
        const localIsNewer =
          Boolean(localLayout && localSavedAt && server.updatedAt) &&
          Date.parse(localSavedAt as string) > Date.parse(server.updatedAt as string);
        const serverIsDefault = isDefaultFurnitureLayout(serverLayout);
        const shouldRecoverLocal =
          Boolean(localLayout) &&
          !isDefaultFurnitureLayout(localLayout as FurnitureItem[]) &&
          (localIsNewer || (!localSavedAt && serverIsDefault));
        const nextLayout = shouldRecoverLocal ? (localLayout as FurnitureItem[]) : serverLayout;

        setFurniture(nextLayout);
        saveFurniture(nextLayout);
        if (shouldRecoverLocal || nextLayout.length !== server.items.length) {
          setLayoutSaveStatus("saving");
          const ok = await pushServerLayout(nextLayout);
          if (!cancelled) setLayoutSaveStatus(ok ? "saved" : "local-only");
        }
      } else {
        setLayoutSaveStatus("saving");
        const ok = await pushServerLayout(furniture);
        if (!cancelled) setLayoutSaveStatus(ok ? "saved" : "local-only");
      }
      hydratedRef.current = true;
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!hydratedRef.current) return;
    let cancelled = false;
    const timeoutId = window.setTimeout(() => {
      saveFurniture(furniture);
      setLayoutSaveStatus("saving");
      void (async () => {
        const ok = await pushServerLayout(furniture);
        if (!cancelled) setLayoutSaveStatus(ok ? "saved" : "local-only");
      })();
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [furniture]);

  useEffect(() => { setTick(() => makeTick(sim)); }, [sim]);

  useEffect(() => {
    const socket = connectVisualization({
      onStatus: setStatus,
      onEvent: (event) => {
        // Forward visitor.chat events to the social panel.
        if (event.type === "visitor.chat" && visitorChatConsumerRef.current) {
          visitorChatConsumerRef.current(event.payload as unknown as import("../net/api").VisitorChatMessage);
          return;
        }
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

  // Scene background music: starts after the first user interaction (browser
  // autoplay policy), pauses when leaving /scene, resumes on return.
  useEffect(() => {
    initSceneMusic();
    return () => stopSceneMusic();
  }, []);

  agentsRef.current = sim.agents;
  lookupRef.current = new Map(sim.agents.map((a) => [a.id, a]));

  const [camX, camY, camZ] = OVERVIEW_CAMERA;
  const floorW = CANVAS_W * SCALE;
  const floorH = CANVAS_H * SCALE;
  const statusTop = compactChrome ? 64 : 12;
  const viewToolbarTop = compactChrome ? 112 : 64;
  const eventLogMaxHeight = compactChrome
    ? "min(260px, calc(100vh - 190px))"
    : "min(260px, calc(100vh - 130px))";

  // Project world coords back to canvas pixels, snapped to the grid and clamped
  // to the canvas bounds. The clamp matters: a click near the screen edge can
  // raycast onto the floor plane far outside the cafe, which previously let
  // furniture be "placed" at off-canvas coords (e.g. y:-1330) and vanish.
  const worldToCanvas = useCallback((wx: number, wz: number) => ({
    cx: Math.max(0, Math.min(CANVAS_W, snap(Math.round((wx + CANVAS_W * SCALE * 0.5) / SCALE)))),
    cy: Math.max(0, Math.min(CANVAS_H, snap(Math.round((wz + CANVAS_H * SCALE * 0.5) / SCALE)))),
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
    // B1: clicking furniture fires the R3F listener first (sets justSelectedRef),
    // then this native click listener. Skip the reset so drag=moving survives and
    // the follow-cursor drag works. Flag is consumed here (reset to false).
    if (justSelectedRef.current) {
      justSelectedRef.current = false;
      return;
    }
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
    justSelectedRef.current = true;
  }, [editMode]);

  // Single source of truth for the currently-selected item (kept in sync with
  // selectedUid + furniture) so the editor panel can read live rot/lift values.
  const selectedItem = useMemo(
    () => furniture.find((it) => it._uid === selectedUid) ?? null,
    [furniture, selectedUid],
  );

  // Selected-item transforms (ported from Claw3D RetroOffice3D:4862-4895). Both
  // the keyboard handler and the SelectedObjectPanel buttons call these, so the
  // two input paths can never drift. snap() aligns to the grid, normalizeDegrees
  // keeps facing in [0,360), elevation clamps to the same range Claw3D uses.
  const updateSelectedItem = useCallback(
    (updater: (it: FurnitureItem) => FurnitureItem) => {
      if (!selectedUid) return;
      setFurniture((prev) =>
        prev.map((it) => (it._uid === selectedUid ? updater(it) : it)),
      );
    },
    [selectedUid],
  );

  const moveSelectedItem = useCallback(
    (dx: number, dy: number, de = 0) => {
      updateSelectedItem((it) => ({
        ...it,
        x: Math.max(0, Math.min(CANVAS_W, snap(it.x + dx))),
        y: Math.max(0, Math.min(CANVAS_H, snap(it.y + dy))),
        elevation: Math.max(-0.4, Math.min(2.5, (it.elevation ?? 0) + de)),
      }));
      // B2: precise nudge (panel button / keyboard) should end follow-cursor so
      // the result isn't clobbered when the mouse re-enters the canvas. The
      // follow-cursor path is handleFloorMove (setFurniture directly) and never
      // goes through here, so it's unaffected.
      setDrag({ kind: "idle" });
    },
    [updateSelectedItem],
  );

  const rotateSelectedItem = useCallback((deltaDeg: number) => {
    updateSelectedItem((it) => ({
      ...it,
      facing: normalizeDegrees((it.facing ?? 0) + deltaDeg),
    }));
    setDrag({ kind: "idle" });
  }, [updateSelectedItem]);

  const deleteSelectedItem = useCallback(() => {
    if (!selectedUid) return;
    setFurniture((prev) => prev.filter((it) => it._uid !== selectedUid));
    setSelectedUid(null);
  }, [selectedUid]);

  const closeSelectedEditor = useCallback(() => {
    setSelectedUid(null);
    setDrag({ kind: "idle" });
    setGhostPos(null);
    setWallDrawStart(null);
  }, []);

  const resetLayout = useCallback(() => {
    if (!window.confirm("恢复默认布局？当前所有编辑将丢失。")) return;
    setFurniture(DEFAULT_FURNITURE);
    setSelectedUid(null);
  }, []);

  // Outside edit mode, clicking a cafe machine opens its immersive panel.
  const handleMachineActivate = useCallback((item: FurnitureItem) => {
    if (editMode) return;
    if (item.type === "atm") setOverlay("order");
    else if (item.type === "coffee_machine") setOverlay("brewing");
  }, [editMode]);

  useEffect(() => {
    if (!editMode) return;
    const onKey = (e: KeyboardEvent) => {
      // Don't hijack keys while typing in an input/textarea (e.g. the chat box).
      const tag = document.activeElement?.tagName ?? "";
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (!selectedUid) {
        if (e.key === "Escape") { setDrag({ kind: "idle" }); setGhostPos(null); setWallDrawStart(null); }
        return;
      }
      const step = e.shiftKey ? SNAP_GRID * 5 : SNAP_GRID;
      switch (e.key) {
        case "ArrowLeft": e.preventDefault(); moveSelectedItem(-step, 0); break;
        case "ArrowRight": e.preventDefault(); moveSelectedItem(step, 0); break;
        case "ArrowUp": e.preventDefault(); moveSelectedItem(0, -step); break;
        case "ArrowDown": e.preventDefault(); moveSelectedItem(0, step); break;
        case "PageUp": e.preventDefault(); moveSelectedItem(0, 0, ELEVATION_STEP); break;
        case "PageDown": e.preventDefault(); moveSelectedItem(0, 0, -ELEVATION_STEP); break;
        case "[": e.preventDefault(); rotateSelectedItem(-ROTATION_STEP_DEG); break;
        case "]": e.preventDefault(); rotateSelectedItem(ROTATION_STEP_DEG); break;
        case "Delete": case "Backspace": e.preventDefault(); deleteSelectedItem(); break;
        case "Escape": closeSelectedEditor(); break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editMode, selectedUid, moveSelectedItem, rotateSelectedItem, deleteSelectedItem, closeSelectedEditor]);

  const ghostItem = useMemo(() => {
    if (drag.kind !== "placing" || !ghostPos) return null;
    if (drag.itemType === "wall") {
      const { cx, cy } = worldToCanvas(ghostPos[0], ghostPos[2]);
      const start = wallDrawStart ?? { x: cx, y: cy };
      return createWallItem(start, { x: cx, y: cy }, "__wall_ghost__");
    }
    return null;
  }, [drag, ghostPos, wallDrawStart, worldToCanvas]);

  // Dev-only debug panel: r3f-perf performance monitor + leva coordinate grid.
  // Hidden in production. Extend by parameterising FURNITURE_SCALE in
  // office3d/objects/furniture.tsx and binding it through useControls below.
  const debug = useControls("Scene Debug", {
    showGrid: { value: false, label: "坐标网格" },
    gridDivisions: { value: 20, min: 4, max: 100, step: 2, label: "网格密度" },
  });

  return (
    <div style={{ position: "relative", width: "100vw", height: "100vh", background: "#0b0f14" }}>
      <SceneErrorBoundary>
      <Canvas
        shadows
        camera={{ position: [camX, camY, camZ], fov: OVERVIEW_ZOOM, near: 0.1, far: 200 }}
        onCreated={({ camera }) => camera.lookAt(OVERVIEW_TARGET[0], OVERVIEW_TARGET[1], OVERVIEW_TARGET[2])}
      >
        <Suspense fallback={null}>
          <SceneLighting />
          <FloorAndWalls />
          <EvoMapAmbientLayer />
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
                  onClick={() =>
                    editMode
                      ? handleFurniturePointerDown(item._uid)
                      : handleMachineActivate(item)
                  }
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
                onPointerDown={() => handleFurniturePointerDown(item._uid)}
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
          <TrailSystem agentsRef={agentsRef} colorMap={colorMap} />
          <AdaptiveDprController />
          <GameLoop tick={tick} />
        </Suspense>
        {import.meta.env.DEV && (
          <>
            <Perf position="top-left" />
            {debug.showGrid && (
              <gridHelper
                args={[40, debug.gridDivisions, "#ff4040", "#555555"]}
                position={[0, 0.01, 0]}
              />
            )}
          </>
        )}
        <OrbitControls
          ref={orbitRef}
          target={[0, 0, 0]}
          minDistance={6}
          maxDistance={Math.max(floorW, floorH) * 1.4}
          maxPolarAngle={Math.PI / 2.1}
        />
      </Canvas>
      </SceneErrorBoundary>
      <Leva collapsed hidden={!import.meta.env.DEV} />
      <ImmersiveOverlay kind={overlay} onClose={() => setOverlay(null)} />
      <TodayTopicsPanel top={statusTop} wsStatus={status} agentCount={sim.agents.length} />
      <div
        style={{
          position: "absolute",
          top: viewToolbarTop,
          right: 12,
          zIndex: 20,
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "flex-end",
          gap: 6,
          maxWidth: "calc(100vw - 24px)",
        }}
      >
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
        {editMode && layoutSaveStatus !== "idle" && (
          <span
            style={{
              alignSelf: "center",
              padding: "4px 8px",
              fontFamily: "monospace",
              fontSize: 11,
              borderRadius: 6,
              border:
                layoutSaveStatus === "local-only"
                  ? "1px solid rgba(248,113,113,0.45)"
                  : "1px solid rgba(74,222,128,0.35)",
              background:
                layoutSaveStatus === "local-only"
                  ? "rgba(248,113,113,0.16)"
                  : "rgba(74,222,128,0.12)",
              color: layoutSaveStatus === "local-only" ? "#fca5a5" : "#86efac",
            }}
          >
            {LAYOUT_SAVE_TEXT[layoutSaveStatus]}
          </span>
        )}
      </div>
      {editMode && (
        <Palette activeType={drag.kind === "placing" ? drag.itemType : null} onPick={startPlacing} />
      )}
      {editMode && selectedItem && (
        <SelectedObjectPanel
          item={selectedItem}
          onMove={moveSelectedItem}
          onRotate={rotateSelectedItem}
          onClose={closeSelectedEditor}
          onDelete={deleteSelectedItem}
          onReset={resetLayout}
        />
      )}
      <div style={{ position: "absolute", bottom: 12, right: 12, width: "min(360px, calc(100vw - 24px))", maxHeight: eventLogMaxHeight, overflowY: "auto", background: "rgba(8,12,20,0.8)", color: "#cfe0ff", fontFamily: "monospace", fontSize: 11, padding: 8, borderRadius: 6 }}>
        <div style={{ color: "#9fb6d8", fontSize: 11, padding: "0 0 6px", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
          Crossroads Agent Café动态
        </div>
        {events.map((e) => {
          const text = formatSceneEvent(e);
          return (
            <div key={String(e.event_id)} style={{ padding: "4px 0", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
              <span style={{ color: "#f0c060" }}>{text}</span>{" "}
              <span style={{ opacity: 0.6 }}>{new Date(e.created_at).toLocaleTimeString()}</span>
            </div>
          );
        })}
      </div>
      <ChatPanel />
      <VisitorSocialPanel registerChatConsumer={registerChatConsumer} />
    </div>
  );
}
