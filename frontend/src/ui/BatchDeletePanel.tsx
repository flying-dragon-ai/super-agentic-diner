// Batch-delete panel for the 3D cafe editor. Shows every furniture type
// currently in the scene grouped by category, with a count and a per-type
// delete button. Also provides "clear all decorative" and "clear all" actions.
import type { CSSProperties } from "react";
import type { FurnitureItem } from "../office3d/core/types";
import { PALETTE } from "./Palette";

export type BatchDeletePanelProps = {
  furniture: FurnitureItem[];
  onDeleteByType: (type: string) => void;
  onClose: () => void;
};

// Category grouping for the type list.
const TYPE_CATEGORY: Record<string, string> = {
  // 桌椅
  executive_desk: "桌椅",
  desk_cubicle: "桌椅",
  round_table: "桌椅",
  table_rect: "桌椅",
  chair: "桌椅",
  // 沙发休闲
  couch: "沙发休闲",
  couch_v: "沙发休闲",
  beanbag: "沙发休闲",
  // 吧台设备
  coffee_machine: "吧台设备",
  coffee_machine_compact: "吧台设备",
  coffee_machine_grinder: "吧台设备",
  espresso: "吧台设备",
  coffee_cup: "吧台设备",
  fridge: "吧台设备",
  cabinet: "吧台设备",
  stove: "吧台设备",
  sink: "吧台设备",
  microwave: "吧台设备",
  // 机器
  atm: "机器",
  vending: "机器",
  jukebox: "机器",
  evomap_terminal: "机器",
  // 装饰
  plant: "装饰",
  lamp: "装饰",
  whiteboard: "装饰",
  bookshelf: "装饰",
  clock: "装饰",
  trash: "装饰",
  computer: "装饰",
  mug: "装饰",
  // 结构
  wall: "结构",
  door: "结构",
};

const CATEGORY_ORDER = ["桌椅", "沙发休闲", "吧台设备", "机器", "装饰", "结构", "其他"];

const CATEGORY_ICON: Record<string, string> = {
  桌椅: "🪑",
  沙发休闲: "🛋️",
  吧台设备: "☕",
  机器: "🎮",
  装饰: "🪴",
  结构: "🧱",
  其他: "📦",
};

const panelStyle: CSSProperties = {
  position: "absolute",
  top: 64,
  right: 12,
  width: 220,
  maxHeight: "calc(100vh - 140px)",
  overflowY: "auto",
  background: "rgba(8,12,20,0.88)",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 8,
  padding: 10,
  color: "#cfe0ff",
  fontFamily: "monospace",
  fontSize: 11,
  zIndex: 50,
};

const rowStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 6,
  padding: "4px 0",
  borderBottom: "1px solid rgba(255,255,255,0.04)",
};

export function BatchDeletePanel({ furniture, onDeleteByType, onClose }: BatchDeletePanelProps) {
  // Count items per type.
  const counts = new Map<string, number>();
  for (const item of furniture) {
    const key = item.type === "couch" && item.vertical ? "couch_v" : item.type;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  // Group by category.
  const grouped = new Map<string, Array<{ type: string; count: number; label: string; icon: string }>>();
  for (const [type, count] of counts) {
    const cat = TYPE_CATEGORY[type] ?? "其他";
    const entry = PALETTE.find((p) => p.type === type);
    const label = entry?.label ?? type.replaceAll("_", " ");
    const icon = entry?.icon ?? "❓";
    if (!grouped.has(cat)) grouped.set(cat, []);
    grouped.get(cat)!.push({ type, count, label, icon });
  }

  const sortedCategories = [...grouped.keys()].sort(
    (a, b) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b),
  );

  const totalItems = furniture.length;

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ color: "#fca5a5", fontSize: 10, letterSpacing: 2 }}>批量删除 · 共 {totalItems} 件</span>
        <button
          onClick={onClose}
          style={{
            cursor: "pointer",
            padding: "2px 6px",
            fontSize: 11,
            background: "rgba(255,255,255,0.06)",
            color: "#cfe0ff",
            border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: 4,
          }}
        >
          ✕
        </button>
      </div>

      {/* Category groups */}
      {sortedCategories.map((cat) => {
        const items = grouped.get(cat)!;
        const catTotal = items.reduce((s, i) => s + i.count, 0);
        return (
          <div key={cat} style={{ marginBottom: 8 }}>
            <div style={{ color: "#9fb6d8", fontSize: 10, marginBottom: 4 }}>
              {CATEGORY_ICON[cat] ?? "📦"} {cat} ({catTotal})
            </div>
            {items.map(({ type, count, label, icon }) => (
              <div key={type} style={rowStyle}>
                <span style={{ flex: 1, overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis" }}>
                  {icon} {label}
                </span>
                <span style={{ opacity: 0.5, minWidth: 24, textAlign: "right" }}>×{count}</span>
                <button
                  onClick={() => onDeleteByType(type)}
                  title={`删除全部 ${count} 个「${label}」`}
                  style={{
                    cursor: "pointer",
                    padding: "2px 8px",
                    fontSize: 10,
                    background: "rgba(239,68,68,0.16)",
                    color: "#fca5a5",
                    border: "1px solid rgba(239,68,68,0.3)",
                    borderRadius: 3,
                  }}
                >
                  删
                </button>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}
