// Coffee domain -> office mapping. Roles map to fixed desk/area coordinates
// (canvas pixel space, projected to world via toWorld at render time). Actions
// map to 3D behaviors the sim/tick layer interprets.
import type { FacingPoint } from "../office3d/core/types";

// Canvas is 1800x720 (W x H). Cafe layout: bar (left x:0-480),
// 2x2 round-table seating (center x:480-1180), lounge (right x:1200-1750).
// Roles map to fixed standby points inside the canvas; entry/exit at the left-edge door.
export const ROLE_DESK: Record<string, FacingPoint> = {
  // 工位 = 待机点 + 动作锚点(walk_to_counter→cashier 吧台收银, walk_to_table→customer 座位,
  // work→各自工位原地绿圈)。坐标对齐家具分区(2026-06-28 重摆,修「工位 vs 家具」错位:
  // 吧台设施原全挤左上,工位却散在中/右区)。现:吧台三人靠左上吧台/咖啡机/收银区,
  // 服务员+顾客在中间座位区。
  barista: { x: 200, y: 300, facing: Math.PI },   // 吧台区:咖啡机 (130,150) 前下方
  cashier: { x: 350, y: 300, facing: Math.PI },   // 吧台收银位 (=counter):atm (410,220) 前下方
  waiter: { x: 755, y: 480, facing: Math.PI },    // 座位区中央:4 圆桌之间送餐动线
  manager: { x: 480, y: 340, facing: Math.PI },   // 吧台↔座位过渡:主管巡视位
  customer: { x: 755, y: 580, facing: 0 },        // 座位区:顾客入座 (=table)
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

export const ENTRY_POINT: FacingPoint = { x: 60, y: 360, facing: 0 };
export const EXIT_POINT: FacingPoint = { x: 60, y: 360, facing: -Math.PI / 2 };

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
