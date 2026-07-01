// Furniture palette for the 3D editor (Phase 4). Ported concept from Claw3D's
// PALETTE, retuned to cafe-relevant props only (bar / seating / lounge / decor).
// Gym/QA/server/phone/sms entries are deliberately excluded for a single cafe.
import { DOOR_LENGTH, DOOR_THICKNESS, WALL_THICKNESS } from "../office3d/core/constants";

export type PaletteEntry = {
  type: string;
  label: string;
  icon: string;
  defaults: Record<string, unknown>;
};

export const PALETTE: PaletteEntry[] = [
  { type: "wall", label: "墙壁", icon: "🧱", defaults: { w: 80, h: WALL_THICKNESS } },
  { type: "door", label: "门", icon: "🚪", defaults: { w: DOOR_LENGTH, h: DOOR_THICKNESS, facing: 0 } },
  { type: "executive_desk", label: "吧台桌", icon: "📋", defaults: { w: 130, h: 65 } },
  { type: "desk_cubicle", label: "办公桌", icon: "🖥️", defaults: { w: 100, h: 55 } },
  { type: "round_table", label: "圆桌", icon: "⭕", defaults: { r: 60 } },
  { type: "table_rect", label: "方桌", icon: "🟫", defaults: { w: 80, h: 40 } },
  { type: "chair", label: "椅子", icon: "🪑", defaults: { facing: 0 } },
  { type: "couch", label: "长沙发", icon: "🛋️", defaults: { w: 100, h: 40 } },
  { type: "couch_v", label: "单人沙发", icon: "🛋️", defaults: { w: 40, h: 80, vertical: true } },
  { type: "beanbag", label: "豆袋", icon: "🟠", defaults: { color: "#e65100" } },
  { type: "coffee_machine", label: "咖啡机", icon: "☕", defaults: {} },
  { type: "fridge", label: "冰箱", icon: "🧊", defaults: { w: 40, h: 80 } },
  { type: "cabinet", label: "储物柜", icon: "🗄️", defaults: { w: 200, h: 40 } },
  { type: "bookshelf", label: "书架", icon: "📚", defaults: { w: 80, h: 120 } },
  { type: "plant", label: "盆栽", icon: "🪴", defaults: {} },
  { type: "lamp", label: "落地灯", icon: "💡", defaults: {} },
  { type: "whiteboard", label: "菜单板", icon: "📝", defaults: { w: 12, h: 70, color: "#3e2723" } },
  { type: "trash", label: "垃圾桶", icon: "🗑️", defaults: {} },
  { type: "atm", label: "收银机", icon: "💳", defaults: { w: 42, h: 38 } },
  { type: "vending", label: "售货机", icon: "🥤", defaults: { w: 40, h: 60 } },
  { type: "jukebox", label: "点唱机", icon: "🎵", defaults: { w: 60, h: 40 } },
  { type: "stove", label: "炉灶", icon: "🔥", defaults: { w: 40, h: 40 } },
  { type: "sink", label: "水槽", icon: "🚰", defaults: { w: 40, h: 40 } },
  { type: "coffee_cup", label: "咖啡杯", icon: "☕", defaults: { elevation: 0.5 } },
  { type: "evomap_terminal", label: "进化地图终端", icon: "GEP", defaults: { w: 80, h: 42, facing: 0, color: "#22d3ee" } },
];

export type PaletteProps = {
  onPick: (type: string) => void;
  activeType: string | null;
};

// Collapsible vertical drawer of placeable items. Clicking an item enters
// "placing" mode; the floor raycaster then drops it where the user clicks.
export function Palette({ onPick, activeType }: PaletteProps) {
  return (
    <div
      style={{
        position: "absolute",
        left: 12,
        top: 64,
        bottom: 12,
        width: 168,
        overflowY: "auto",
        background: "rgba(8,12,20,0.82)",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 8,
        padding: 8,
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 6,
        alignContent: "start",
      }}
    >
      {PALETTE.map((entry) => {
        const active = entry.type === activeType;
        return (
          <button
            key={entry.type}
            title={entry.label}
            onClick={() => onPick(entry.type)}
            style={{
              cursor: "pointer",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 2,
              padding: "8px 4px",
              fontSize: 11,
              fontFamily: "monospace",
              color: active ? "#fbbf24" : "#cfe0ff",
              background: active ? "rgba(251,191,36,0.16)" : "rgba(255,255,255,0.03)",
              border: active ? "1px solid #fbbf24" : "1px solid rgba(255,255,255,0.08)",
              borderRadius: 6,
            }}
          >
            <span style={{ fontSize: 18 }}>{entry.icon}</span>
            <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 64 }}>
              {entry.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
