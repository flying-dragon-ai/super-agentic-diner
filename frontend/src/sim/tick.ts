// Per-frame movement simulation. Simplified port of Claw3D's RetroOffice3D
// tick(): walk agents along their A* path toward target, advance the animation
// frame counter, settle into sitting/standing at destination. No Claw3D-specific
// janitor/pingpong/gym logic.
import {
  BUMP_RECOVERY_MS,
  CANVAS_H,
  CANVAS_W,
  SNAP_GRID,
  WALK_SPEED,
} from "../office3d/core/constants";
import { ROAM_POINTS, astar } from "../office3d/core/navigation";
import { applyAgentCollisionBumps } from "../office3d/systems/NavigationSystem";
import { getDeskLocations } from "./agentStore";
import type { SimHandle } from "./agentStore";
import type { RenderAgent } from "../office3d/core/types";

const ARRIVAL_THRESHOLD = 4;
const AWAY_THRESHOLD_MS = 15 * 60 * 1000;
const SOCIAL_ROAM_PROBABILITY = 0.005;
const SOCIAL_FURNITURE_PROBABILITY = 0.15;

const isSocialFurniture = (type: string) =>
  ["couch", "couch_v", "beanbag", "coffee_machine", "water_cooler"].includes(type);
const isAwayFurniture = (type: string) =>
  ["couch", "couch_v", "beanbag"].includes(type);
const isCustomerAgent = (agent: RenderAgent) => agent.role === "customer";

const snapClamp = (v: number) =>
  Math.max(SNAP_GRID, Math.min(CANVAS_W - SNAP_GRID, Math.round(v / SNAP_GRID) * SNAP_GRID));
const snapClampY = (v: number) =>
  Math.max(SNAP_GRID, Math.min(CANVAS_H - SNAP_GRID, Math.round(v / SNAP_GRID) * SNAP_GRID));

const moveAlongPath = (agent: RenderAgent) => {
  agent.frame += 1;
  if (agent.path.length === 0) return false;
  const next = agent.path[0];
  const dx = next.x - agent.x;
  const dy = next.y - agent.y;
  const dist = Math.hypot(dx, dy);
  if (dist < ARRIVAL_THRESHOLD) {
    agent.path.shift();
    if (agent.path.length === 0) return true;
    return false;
  }
  const step = Math.min(WALK_SPEED * 60, dist);
  agent.x += (dx / dist) * step;
  agent.y += (dy / dist) * step;
  agent.facing = Math.atan2(dx, dy);
  agent.state = "walking";
  return false;
};

// Decide the next intent for an agent that has finished walking: seated vs
// standing, away (idle > 15 min -> nearest couch), dancing (external trigger),
// or an occasional social stroll toward lounge furniture / roam points.
const settleIdle = (
  agent: RenderAgent,
  nav: Uint8Array,
  deskLocs: { x: number; y: number }[],
  socialFurniture: { x: number; y: number; type: string }[],
  awayFurniture: { x: number; y: number }[],
  now: number,
) => {
  const nearDesk = deskLocs.some((d) => Math.hypot(d.x - agent.x, d.y - agent.y) < 50);
  if (agent.status === "working") {
    agent.state = nearDesk ? "sitting" : "standing";
    return;
  }
  if (agent.status === "error") {
    agent.state = "standing";
    return;
  }
  // Dance trigger wins over away/standing.
  if ((agent.danceUntil ?? 0) > now) {
    agent.state = "dancing";
    agent.path = [];
    return;
  }
  // Customers should move only when backend visualization events direct them
  // (enter, walk_to_counter/table, leave). Letting idle customers join the
  // staff social-roam loop makes visitors drift across the whole cafe.
  if (isCustomerAgent(agent)) {
    agent.state = "standing";
    return;
  }
  // Away: idle for > AWAY_THRESHOLD_MS -> route to nearest couch/beanbag.
  const lastSeen = agent.lastSeenAt ?? now;
  const isAway = lastSeen > 0 && now - lastSeen > AWAY_THRESHOLD_MS;
  if (isAway && agent.state !== "away" && awayFurniture.length > 0) {
    const f = awayFurniture[Math.floor(Math.random() * awayFurniture.length)];
    const tx = snapClamp(f.x + 20);
    const ty = snapClampY(f.y + 20);
    agent.path = astar(agent.x, agent.y, tx, ty, nav);
    agent.targetX = tx;
    agent.targetY = ty;
    agent.state = agent.path.length > 0 ? "walking" : "away";
    return;
  }
  agent.state = isAway ? "away" : "standing";
  // Occasional social stroll: walk to lounge furniture or a roam point.
  if (!isAway && Math.random() < SOCIAL_ROAM_PROBABILITY) {
    let target: { x: number; y: number } | null = null;
    if (socialFurniture.length > 0 && Math.random() < SOCIAL_FURNITURE_PROBABILITY) {
      const f = socialFurniture[Math.floor(Math.random() * socialFurniture.length)];
      target = { x: f.x + 20, y: f.y + 20 };
    } else {
      target = ROAM_POINTS[Math.floor(Math.random() * ROAM_POINTS.length)];
    }
    if (target) {
      const tx = snapClamp(target.x);
      const ty = snapClampY(target.y);
      agent.path = astar(agent.x, agent.y, tx, ty, nav);
      agent.targetX = tx;
      agent.targetY = ty;
      agent.state = agent.path.length > 0 ? "walking" : agent.state;
    }
  }
};

export function makeTick(handle: SimHandle) {
  return () => {
    const now = Date.now();
    const deskLocs = getDeskLocations(handle.furniture);
    const nav = handle._nav;
    const socialFurniture = handle.furniture
      .filter((f) => isSocialFurniture(f.type))
      .map((f) => ({ x: f.x, y: f.y, type: f.type }));
    const awayFurniture = handle.furniture
      .filter((f) => isAwayFurniture(f.type))
      .map((f) => ({ x: f.x, y: f.y }));
    for (const agent of handle.agents) {
      // Bumped agents freeze until their timer expires, then resume with a brief
      // collision cooldown so the overlapping pair peel apart cleanly.
      if (agent.bumpedUntil !== undefined) {
        agent.frame += 1;
        agent.state = "standing";
        if (now >= agent.bumpedUntil) {
          agent.bumpedUntil = undefined;
          agent.collisionCooldownUntil = now + BUMP_RECOVERY_MS;
        }
        continue;
      }
      moveAlongPath(agent);
      if (agent.path.length === 0) {
        settleIdle(agent, nav, deskLocs, socialFurniture, awayFurniture, now);
      }
    }
    // Resolve overlaps: freeze + reroute overlapping walkers in different directions.
    const bumped = applyAgentCollisionBumps({ agents: handle.agents, now });
    handle.agents.splice(0, handle.agents.length, ...bumped);
  };
}
