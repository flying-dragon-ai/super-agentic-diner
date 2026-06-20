// Coffee domain -> office mapping. Roles map to fixed desk/area coordinates
// (canvas pixel space, projected to world via toWorld at render time). Actions
// map to 3D behaviors the sim/tick layer interprets.
import type { FacingPoint } from "../office3d/core/types";

// Canvas is 1800x1800. Desks spread across the floor; entry at left edge.
export const ROLE_DESK: Record<string, FacingPoint> = {
  barista: { x: 360, y: 540, facing: Math.PI },
  cashier: { x: 620, y: 320, facing: Math.PI },
  waiter: { x: 880, y: 700, facing: Math.PI },
  manager: { x: 1180, y: 320, facing: Math.PI },
  customer: { x: 880, y: 1080, facing: 0 },
};

export const ROLE_COLOR: Record<string, string> = {
  barista: "#a8722a",
  cashier: "#2a6ba8",
  waiter: "#2a8a5e",
  manager: "#8a2a6b",
  customer: "#6b6f76",
};

export const ROLE_LABEL: Record<string, string> = {
  barista: "咖啡师",
  cashier: "收银员",
  waiter: "服务员",
  manager: "主管",
  customer: "访客",
};

export const ENTRY_POINT: FacingPoint = { x: 60, y: 900, facing: 0 };
export const EXIT_POINT: FacingPoint = { x: 60, y: 900, facing: -Math.PI / 2 };

export type ActionBehavior =
  | "enter"
  | "walk_to_counter"
  | "walk_to_table"
  | "work"
  | "deliver"
  | "show_message"
  | "leave"
  | "error";

export const ACTION_BEHAVIOR: Record<string, ActionBehavior> = {
  enter_scene: "enter",
  walk_to_counter: "walk_to_counter",
  walk_to_table: "walk_to_table",
  take_order: "work",
  prepare_coffee: "work",
  deliver_order: "deliver",
  show_message: "show_message",
  leave_scene: "leave",
  error: "error",
};

export const resolveRole = (role: string): string =>
  ROLE_DESK[role] ? role : "customer";
export const resolveAction = (action: string): ActionBehavior =>
  ACTION_BEHAVIOR[action] ?? "walk_to_table";
