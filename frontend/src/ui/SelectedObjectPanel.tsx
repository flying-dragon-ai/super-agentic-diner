// Selected-object editor panel for the 3D cafe editor. Ported from Claw3D
// RetroOffice3D's object editor (:6801-6927), cafe-localised and without the
// desk-assignment dropdown. Renders a clickable Move 3x3 grid + Rotate +/-15°
// buttons + close/delete/reset so mouse users can edit without memorising the
// keyboard shortcuts. Keyboard handling lives in OfficeScene and shares the
// same onMove/onRotate callbacks, so both input paths stay in sync.
import type { CSSProperties } from "react";
import {
  ELEVATION_STEP,
  ROTATION_STEP_DEG,
  SNAP_GRID,
} from "../office3d/core/constants";
import type { FurnitureItem } from "../office3d/core/types";
import { PALETTE } from "./Palette";

export type SelectedObjectPanelProps = {
  item: FurnitureItem;
  onMove: (dx: number, dy: number, de?: number) => void;
  onRotate: (deltaDeg: number) => void;
  onClose: () => void;
  onDelete: () => void;
  onReset: () => void;
};

const sectionLabel: CSSProperties = {
  color: "#fbbf24",
  fontSize: 10,
  letterSpacing: 2,
  textTransform: "uppercase",
  margin: "10px 0 4px",
};

// Shared look for the Move/Rotate grid buttons.
const gridBtn: CSSProperties = {
  cursor: "pointer",
  padding: "6px 0",
  fontSize: 11,
  fontFamily: "monospace",
  color: "#cfe0ff",
  background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 5,
};

export function SelectedObjectPanel({
  item,
  onMove,
  onRotate,
  onClose,
  onDelete,
  onReset,
}: SelectedObjectPanelProps) {
  const label =
    PALETTE.find((p) => p.type === item.type)?.label ??
    item.type.replaceAll("_", " ");
  const rot = Math.round(item.facing ?? 0);
  const lift = (item.elevation ?? 0).toFixed(2);

  return (
    <div
      style={{
        position: "absolute",
        bottom: 12,
        left: 192,
        width: 176,
        color: "#cfe0ff",
        fontFamily: "monospace",
        fontSize: 11,
        background: "rgba(8,12,20,0.85)",
        padding: 10,
        borderRadius: 6,
        border: "1px solid rgba(255,255,255,0.08)",
      }}
    >
      {/* Header: label + live rot/lift readout + close button. */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 8,
        }}
      >
        <div>
          <div style={{ color: "#fbbf24", fontSize: 10, letterSpacing: 2 }}>
            已选中
          </div>
          <div style={{ color: "#e8dfc0", marginTop: 2 }}>{label}</div>
          <div style={{ opacity: 0.6, marginTop: 2 }}>
            rot {rot}° · lift {lift}
          </div>
        </div>
        <button
          onClick={onClose}
          title="关闭"
          style={{
            cursor: "pointer",
            padding: "2px 6px",
            fontSize: 11,
            fontFamily: "monospace",
            background: "rgba(255,255,255,0.06)",
            color: "#cfe0ff",
            border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: 4,
          }}
        >
          ✕
        </button>
      </div>

      {/* Move 3x3: empty / 前 / empty · 左 / 抬升 / 右 · empty / 后 / 下降. */}
      <div style={sectionLabel}>移动</div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: 4,
        }}
      >
        <span />
        <button style={gridBtn} onClick={() => onMove(0, -SNAP_GRID)}>
          ↑ 前
        </button>
        <span />
        <button style={gridBtn} onClick={() => onMove(-SNAP_GRID, 0)}>
          ← 左
        </button>
        <button
          style={gridBtn}
          onClick={() => onMove(0, 0, ELEVATION_STEP)}
          title="抬高 (PgUp)"
        >
          抬升
        </button>
        <button style={gridBtn} onClick={() => onMove(SNAP_GRID, 0)}>
          右 →
        </button>
        <span />
        <button style={gridBtn} onClick={() => onMove(0, SNAP_GRID)}>
          ↓ 后
        </button>
        <button
          style={gridBtn}
          onClick={() => onMove(0, 0, -ELEVATION_STEP)}
          title="降低 (PgDn)"
        >
          下降
        </button>
      </div>

      {/* Rotate -15° / +15°. */}
      <div style={sectionLabel}>旋转</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
        <button
          style={gridBtn}
          onClick={() => onRotate(-ROTATION_STEP_DEG)}
          title="逆时针 ([)"
        >
          −{ROTATION_STEP_DEG}°
        </button>
        <button
          style={gridBtn}
          onClick={() => onRotate(ROTATION_STEP_DEG)}
          title="顺时针 (])"
        >
          +{ROTATION_STEP_DEG}°
        </button>
      </div>
      <div style={{ opacity: 0.6, marginTop: 4 }}>
        方向键移动 · PgUp/Dn 抬升 · [ ] 旋转 · Del 删除 · Esc 取消
      </div>

      {/* Delete / Reset to default. */}
      <div style={{ marginTop: 8, display: "flex", gap: 6 }}>
        <button
          onClick={onDelete}
          style={{
            cursor: "pointer",
            flex: 1,
            padding: "4px 0",
            fontSize: 11,
            fontFamily: "monospace",
            background: "rgba(239,68,68,0.18)",
            color: "#fca5a5",
            border: "1px solid rgba(239,68,68,0.4)",
            borderRadius: 4,
          }}
        >
          删除
        </button>
        <button
          onClick={onReset}
          style={{
            cursor: "pointer",
            flex: 1,
            padding: "4px 0",
            fontSize: 11,
            fontFamily: "monospace",
            background: "rgba(96,165,250,0.18)",
            color: "#93c5fd",
            border: "1px solid rgba(96,165,250,0.4)",
            borderRadius: 4,
          }}
        >
          恢复默认
        </button>
      </div>
    </div>
  );
}
