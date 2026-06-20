// agent_id -> live RenderAgent state machine. The visualization events from
// /ws/visualization push intents (enter/walk/work/deliver/message/leave/error)
// into the store; tick() then advances motion toward those intents.
import { astar, buildNavGrid, getDeskLocations, ENTRY_POINT as NAV_ENTRY } from "../office3d/core/navigation";
import type { FurnitureItem, RenderAgent } from "../office3d/core/types";
import { ENTRY_POINT, EXIT_POINT, ROLE_COLOR, ROLE_DESK, ROLE_LABEL, resolveAction, resolveRole } from "./roleMap";

void NAV_ENTRY;

export type AgentMeta = {
  id: string;
  name: string;
  subtitle: string | null;
  role: string;
  color: string;
  spriteSeed: number;
};

export type SimHandle = {
  agents: RenderAgent[];
  furniture: FurnitureItem[];
  speech: Map<string, string>;
  rebuildNav: () => void;
  setFurniture: (items: FurnitureItem[]) => void;
  _nav: Uint8Array;
};

export function createSimStore(): SimHandle {
  const handle: SimHandle = {
    agents: [],
    furniture: [],
    speech: new Map(),
    rebuildNav: () => {
      handle._nav = buildNavGrid(handle.furniture);
    },
    setFurniture: (items) => {
      handle.furniture = items;
      handle._nav = buildNavGrid(items);
    },
    _nav: new Uint8Array(0),
  };
  return handle;
}

export function getNav(handle: SimHandle): Uint8Array {
  return handle._nav;
}

const ensureAgent = (handle: SimHandle, meta: AgentMeta): RenderAgent => {
  let agent = handle.agents.find((a) => a.id === meta.id);
  const role = resolveRole(meta.role);
  if (!agent) {
    const desk = ROLE_DESK[role];
    agent = {
      id: meta.id,
      name: meta.name,
      subtitle: meta.subtitle,
      status: "idle",
      color: meta.color || ROLE_COLOR[role],
      item: role,
      role,
      x: ENTRY_POINT.x,
      y: ENTRY_POINT.y,
      targetX: ENTRY_POINT.x,
      targetY: ENTRY_POINT.y,
      path: [],
      facing: ENTRY_POINT.facing,
      frame: 0,
      walkSpeed: 1,
      phaseOffset: (meta.spriteSeed % 100) / 100,
      state: "standing",
    };
    handle.agents.push(agent);
  }
  return agent;
};

const routeTo = (handle: SimHandle, agent: RenderAgent, tx: number, ty: number) => {
  const nav = getNav(handle);
  agent.path = astar(agent.x, agent.y, tx, ty, nav);
  agent.targetX = tx;
  agent.targetY = ty;
  agent.state = agent.path.length > 0 ? "walking" : agent.state;
};

// Apply a visualization event's action to an agent's intent.
export function applyEvent(
  handle: SimHandle,
  meta: AgentMeta,
  action: string,
  payload: Record<string, unknown>,
) {
  const agent = ensureAgent(handle, meta);
  const behavior = resolveAction(action);
  const role = resolveRole(meta.role);
  agent.status = behavior === "error" ? "error" : agent.status === "error" ? "idle" : agent.status;

  switch (behavior) {
    case "enter": {
      agent.x = ENTRY_POINT.x;
      agent.y = ENTRY_POINT.y;
      routeTo(handle, agent, ROLE_DESK[role].x, ROLE_DESK[role].y);
      break;
    }
    case "walk_to_counter": {
      routeTo(handle, agent, ROLE_DESK.cashier.x, ROLE_DESK.cashier.y);
      break;
    }
    case "walk_to_table": {
      const tx = typeof payload.x === "number" ? payload.x : ROLE_DESK.customer.x;
      const ty = typeof payload.y === "number" ? payload.y : ROLE_DESK.customer.y;
      routeTo(handle, agent, tx, ty);
      break;
    }
    case "work": {
      const desk = ROLE_DESK[role];
      if (Math.hypot(agent.x - desk.x, agent.y - desk.y) > 60) routeTo(handle, agent, desk.x, desk.y);
      agent.status = "working";
      break;
    }
    case "deliver": {
      routeTo(handle, agent, ROLE_DESK.customer.x, ROLE_DESK.customer.y);
      break;
    }
    case "show_message": {
      const text = typeof payload.text === "string" ? payload.text : "";
      handle.speech.set(agent.id, text);
      break;
    }
    case "leave": {
      agent.status = "idle";
      routeTo(handle, agent, EXIT_POINT.x, EXIT_POINT.y);
      break;
    }
    case "error": {
      agent.status = "error";
      break;
    }
  }
}

export function clearSpeech(handle: SimHandle, id: string) {
  handle.speech.delete(id);
}

// Re-exports for parity with Claw3D getDeskLocations and role constants.
export { getDeskLocations, ROLE_DESK, ROLE_COLOR, ROLE_LABEL, ENTRY_POINT, EXIT_POINT };
