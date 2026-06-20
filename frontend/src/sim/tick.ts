// Per-frame movement simulation. Simplified port of Claw3D's RetroOffice3D
// tick(): walk agents along their A* path toward target, advance the animation
// frame counter, settle into sitting/standing at destination. No Claw3D-specific
// janitor/pingpong/gym logic.
import { WALK_SPEED } from "../office3d/core/constants";
import { getDeskLocations } from "./agentStore";
import type { SimHandle } from "./agentStore";
import type { RenderAgent } from "../office3d/core/types";

const ARRIVAL_THRESHOLD = 4;

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

export function makeTick(handle: SimHandle) {
  return () => {
    const deskLocs = getDeskLocations(handle.furniture);
    for (const agent of handle.agents) {
      const arrived = moveAlongPath(agent);
      if (agent.path.length === 0) {
        // Arrived or idle: decide seated vs standing based on proximity to a desk.
        const nearDesk = deskLocs.some((d) => Math.hypot(d.x - agent.x, d.y - agent.y) < 50);
        if (agent.status === "working") {
          agent.state = nearDesk ? "sitting" : "standing";
        } else if (agent.state === "walking" || arrived) {
          agent.state = "standing";
        }
      }
    }
  };
}
