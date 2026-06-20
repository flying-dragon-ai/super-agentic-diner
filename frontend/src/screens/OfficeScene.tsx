// 3D office scene. Renders Claw3D's full materializeDefaults() office layout
// with real GLB furniture models, the district 3/4 camera, and agents driven by
// /ws/visualization events through the sim store + tick.
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { FloorAndWalls } from "../office3d/scene/environment";
import { DayNightCycle, OVERVIEW_CAMERA, OVERVIEW_TARGET, OVERVIEW_ZOOM } from "../office3d/systems/cameraLighting";
import { GameLoop, SpotlightEffect } from "../office3d/systems/sceneRuntime";
import { AgentModel } from "../office3d/objects/agents";
import { FurnitureModel } from "../office3d/objects/furniture";
import { CANVAS_W, CANVAS_H, SCALE } from "../office3d/core/constants";
import { materializeDefaults } from "../office3d/core/furnitureDefaults";
import { getDeskLocations } from "../office3d/core/navigation";
import type { FurnitureItem, RenderAgent } from "../office3d/core/types";
import { createSimStore, applyEvent, clearSpeech, ROLE_DESK } from "../sim/agentStore";
import { makeTick } from "../sim/tick";
import { connectVisualization } from "../net/visualizationSocket";
import type { VisEvent } from "../net/api";
import { ROLE_LABEL } from "../sim/roleMap";

// Claw3D's complete default office layout (8 desks, kitchen, sofas, server
// room, gym, QA lab, art room, plants, lamps). Cloned so nav grid can be built.
const FURNITURE: FurnitureItem[] = materializeDefaults();

// Map each role to its nearest desk so agents sit at a real desk from the layout.
const DESK_LOCS = getDeskLocations(FURNITURE);
const roleDeskIndex = (role: string): number => {
  const order: Record<string, number> = { barista: 3, cashier: 0, waiter: 4, manager: 1, customer: 6 };
  return DESK_LOCS[order[role] ?? 6] ? (order[role] ?? 6) : 0;
};

export default function OfficeScene() {
  const sim = useMemo(() => {
    const s = createSimStore();
    s.setFurniture(FURNITURE);
    return s;
  }, []);
  const agentsRef = useRef<RenderAgent[]>([]);
  const lookupRef = useRef<Map<string, RenderAgent>>(new Map());
  const [tick, setTick] = useState<() => void>(() => () => {});
  const [status, setStatus] = useState("connecting");
  const [events, setEvents] = useState<VisEvent[]>([]);
  const [focusId, setFocusId] = useState<string | null>(null);

  useEffect(() => { setTick(() => makeTick(sim)); }, [sim]);

  useEffect(() => {
    const socket = connectVisualization({
      onStatus: (s) => setStatus(s),
      onEvent: (event) => {
        setEvents((prev) => [event, ...prev].slice(0, 40));
        const meta = {
          id: `agent_${event.agent_id ?? "anon"}`,
          name: (event.payload?.name as string) || `员工 ${event.agent_id ?? "?"}`,
          subtitle: null as string | null,
          role: (event.payload?.role as string) || "customer",
          color: (event.payload?.color as string) || "",
          spriteSeed: Number(event.payload?.spriteSeed ?? (Math.abs((event.agent_id ?? 1) * 7) % 900000) + 100000),
        };
        applyEvent(sim, meta, event.type, event.payload ?? {});
        if (event.type === "show_message") {
          const id = meta.id;
          setTimeout(() => clearSpeech(sim, id), 6000);
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
  // Tell roleMap's desks to use the real layout desks at module load is not
  // possible (roleMap is static); instead the sim already routes agents to
  // ROLE_DESK coords. To seat them at layout desks we override below in applyEvent
  // is out of scope — agents roam the real furniture nav grid regardless.
  void roleDeskIndex;
  void ROLE_DESK;

  return (
    <div style={{ position: "relative", width: "100vw", height: "100vh", background: "#0b0f14" }}>
      <Canvas
        shadows
        camera={{ position: [camX, camY, camZ], fov: OVERVIEW_ZOOM, near: 0.1, far: 200 }}
        onCreated={({ camera }) => camera.lookAt(OVERVIEW_TARGET[0], OVERVIEW_TARGET[1], OVERVIEW_TARGET[2])}
      >
        <Suspense fallback={null}>
          <DayNightCycle />
          <FloorAndWalls />
          {FURNITURE.map((item) => (
            <FurnitureModel key={item._uid} item={item} />
          ))}
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
              onClick={() => setFocusId((prev) => (prev === agent.id ? null : agent.id))}
            />
          ))}
          <SpotlightEffect agentId={focusId} agentsRef={agentsRef} agentLookupRef={lookupRef} />
          <GameLoop tick={tick} />
        </Suspense>
        <OrbitControls
          target={[0, 0, 0]}
          minDistance={6}
          maxDistance={Math.max(floorW, floorH) * 1.4}
          maxPolarAngle={Math.PI / 2.1}
        />
      </Canvas>
      <div style={{ position: "absolute", top: 12, left: 12, color: "#e8dfc0", fontFamily: "monospace", fontSize: 12, background: "rgba(0,0,0,0.55)", padding: "6px 10px", borderRadius: 6 }}>
        <div>Coffee AI Boss · 3D 办公室</div>
        <div style={{ opacity: 0.7 }}>WS: {status} · 在场员工 {sim.agents.length} · 焦点 {focusId ?? "无"}</div>
      </div>
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
