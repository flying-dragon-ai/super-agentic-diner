// Immersive overlay (Phase 5d). Adapted from Claw3D's MonitorImmersiveContent
// concept (ESC-close, focus panel) but retuned to cafe business — clicking the
// register ATM opens an order detail panel, clicking the coffee machine opens a
// stock/brewing panel. Pure HTML overlay (no VSCode mock); content is cafe-only.
import { useEffect } from "react";

export type OverlayKind = "order" | "brewing" | null;

export type ImmersiveOverlayProps = {
  kind: OverlayKind;
  onClose: () => void;
};

const ORDER_SAMPLES = [
  { id: "#1042", item: "拿铁 Latte", amount: 25, status: "制作中", source: "web" },
  { id: "#1041", item: "美式 Americano", amount: 18, status: "已完成", source: "skill" },
  { id: "#1040", item: "卡布奇诺 Cappuccino", amount: 24, status: "待接单", source: "web" },
  { id: "#1039", item: "摩卡 Mocha", amount: 28, status: "已完成", source: "skill" },
];

const STOCK = [
  { name: "咖啡豆", level: 78, unit: "%" },
  { name: "牛奶", level: 45, unit: "%" },
  { name: "糖浆", level: 62, unit: "%" },
  { name: "纸杯 (中)", level: 30, unit: "个" },
];

const PRODUCTION_QUEUE = [
  { station: "萃取工位", order: "#1042 拿铁", status: "制作中", eta: "02:10" },
  { station: "奶泡工位", order: "#1040 卡布奇诺", status: "待制作", eta: "等待" },
  { station: "出品工位", order: "#1039 摩卡", status: "已完成", eta: "待取餐" },
];

const systemPanelStyle = {
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 8,
  padding: 12,
  background: "rgba(255,255,255,0.03)",
};

// Full-screen darkened backdrop + centered panel. ESC or backdrop click closes.
export function ImmersiveOverlay({ kind, onClose }: ImmersiveOverlayProps) {
  useEffect(() => {
    if (!kind) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [kind, onClose]);

  if (!kind) return null;

  return (
    <div
      onClick={onClose}
      style={{
        position: "absolute",
        inset: 0,
        background: "rgba(4,8,14,0.72)",
        backdropFilter: "blur(2px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 680,
          maxWidth: "92vw",
          maxHeight: "82vh",
          overflowY: "auto",
          background: "linear-gradient(180deg,#141d2b,#0d1420)",
          border: "1px solid rgba(240,192,96,0.25)",
          borderRadius: 12,
          color: "#e8dfc0",
          fontFamily: "monospace",
          padding: 20,
          boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h2 style={{ margin: 0, fontSize: 16, color: "#f0c060" }}>
            {kind === "order" ? "🧾 订单详情" : "☕ 库存系统 · 制作系统"}
          </h2>
          <button
            onClick={onClose}
            style={{
              cursor: "pointer",
              background: "rgba(255,255,255,0.06)",
              color: "#cfe0ff",
              border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 6,
              padding: "4px 10px",
              fontFamily: "monospace",
            }}
          >
            ✕ 关闭 (Esc)
          </button>
        </div>
        {kind === "order" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {ORDER_SAMPLES.map((o) => (
              <div
                key={o.id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "10px 12px",
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.06)",
                  borderRadius: 8,
                }}
              >
                <div>
                  <div style={{ color: "#e8dfc0" }}>{o.item}</div>
                  <div style={{ fontSize: 11, opacity: 0.6 }}>
                    {o.id} · 来源 {o.source}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ color: "#f0c060" }}>¥{o.amount.toFixed(2)}</div>
                  <div
                    style={{
                      fontSize: 11,
                      color:
                        o.status === "已完成"
                          ? "#4ade80"
                          : o.status === "制作中"
                            ? "#f0c060"
                            : "#93c5fd",
                    }}
                  >
                    {o.status}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span style={{ padding: "4px 8px", borderRadius: 999, background: "rgba(74,222,128,0.14)", color: "#86efac", border: "1px solid rgba(74,222,128,0.28)", fontSize: 12 }}>
                库存系统
              </span>
              <span style={{ padding: "4px 8px", borderRadius: 999, background: "rgba(96,165,250,0.14)", color: "#93c5fd", border: "1px solid rgba(96,165,250,0.28)", fontSize: 12 }}>
                制作系统
              </span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
              <section style={systemPanelStyle}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
                  <div style={{ color: "#86efac", fontSize: 13, fontWeight: 700 }}>库存系统</div>
                  <div style={{ color: "#9fb6d8", fontSize: 11 }}>原料余量</div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {STOCK.map((s) => (
                    <div key={s.name}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                        <span>{s.name}</span>
                        <span style={{ color: "#f0c060" }}>
                          {s.level}
                          {s.unit}
                        </span>
                      </div>
                      <div style={{ height: 8, background: "rgba(255,255,255,0.08)", borderRadius: 4, overflow: "hidden" }}>
                        <div
                          style={{
                            width: `${Math.min(100, s.level)}%`,
                            height: "100%",
                            background:
                              s.level < 35 ? "linear-gradient(90deg,#ef4444,#f97316)" : "linear-gradient(90deg,#f0c060,#4ade80)",
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </section>
              <section style={systemPanelStyle}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
                  <div style={{ color: "#93c5fd", fontSize: 13, fontWeight: 700 }}>制作系统</div>
                  <div style={{ color: "#9fb6d8", fontSize: 11 }}>咖啡出品队列</div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {PRODUCTION_QUEUE.map((step) => (
                    <div
                      key={step.station}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "72px 1fr auto",
                        gap: 8,
                        alignItems: "center",
                        padding: "8px 0",
                        borderBottom: "1px solid rgba(255,255,255,0.06)",
                      }}
                    >
                      <span style={{ color: "#93c5fd", fontSize: 12 }}>{step.station}</span>
                      <span style={{ color: "#e8dfc0", fontSize: 12 }}>{step.order}</span>
                      <span style={{ color: step.status === "已完成" ? "#4ade80" : step.status === "制作中" ? "#f0c060" : "#9fb6d8", fontSize: 12 }}>
                        {step.status} · {step.eta}
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
