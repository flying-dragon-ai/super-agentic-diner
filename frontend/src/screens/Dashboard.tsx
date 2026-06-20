// Big-screen dashboard. Aggregates /admin/restaurant-state (today's order count
// + amount, source split, recent orders/events, active agents/consumers) and a
// recent event feed, on a dark monitoring-friendly layout.
import { useEffect, useState } from "react";
import { getRestaurantState, listEvents, type VisEvent } from "../net/api";

type State = {
  today?: { order_count?: number; total_amount?: number; active_agent_count?: number; active_consumer_count?: number };
  by_source?: { source_type: string; count: number; amount: number }[];
  recent_orders?: { order_id: number; coffee_name: string; amount: number; status: number; source_type: string; created_at: string }[];
  recent_events?: VisEvent[];
  agents?: { display_name?: string; role_type?: string; status?: string }[];
};

const card: React.CSSProperties = { background: "rgba(14,22,34,0.9)", border: "1px solid rgba(80,130,200,0.18)", borderRadius: 10, padding: 18 };
const label: React.CSSProperties = { color: "#7fa6d8", fontSize: 12, letterSpacing: 2, textTransform: "uppercase" };
const num: React.CSSProperties = { color: "#e8dfc0", fontSize: 34, fontWeight: 700, fontFamily: "monospace" };

export default function Dashboard() {
  const [state, setState] = useState<State | null>(null);
  const [events, setEvents] = useState<VisEvent[]>([]);

  useEffect(() => {
    const load = () => {
      getRestaurantState().then((s) => setState(s as State)).catch(() => {});
      listEvents(30).then(setEvents).catch(() => {});
    };
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  const recentEvents = events.length ? events : (state?.recent_events ?? []);
  const today = state?.today;

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#080c12", color: "#dfe8f5", fontFamily: "system-ui, sans-serif", padding: 24, boxSizing: "border-box", overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 24, letterSpacing: 2 }}>Coffee AI Boss · 实时监控大屏</h1>
        <span style={{ color: "#7fa6d8", fontSize: 13 }}>{new Date().toLocaleString("zh-CN")}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 16 }}>
        <div style={card}><div style={label}>今日订单</div><div style={num}>{today?.order_count ?? "—"}</div></div>
        <div style={card}><div style={label}>今日金额</div><div style={num}>¥{today?.total_amount != null ? Number(today.total_amount).toFixed(2) : "—"}</div></div>
        <div style={card}><div style={label}>在线员工</div><div style={num}>{today?.active_agent_count ?? state?.agents?.length ?? "—"}</div></div>
        <div style={card}><div style={label}>活跃访客</div><div style={num}>{today?.active_consumer_count ?? "—"}</div></div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1.4fr", gap: 16 }}>
        <div style={card}>
          <div style={{ ...label, marginBottom: 12 }}>最近订单</div>
          {(state?.recent_orders ?? []).map((o) => (
            <div key={o.order_id} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", fontFamily: "monospace", fontSize: 13 }}>
              <span style={{ color: "#e8dfc0" }}>{o.coffee_name}</span>
              <span style={{ color: "#9fb6d8" }}>{o.source_type}</span>
              <span style={{ color: "#f0c060" }}>¥{Number(o.amount).toFixed(2)}</span>
              <span style={{ opacity: 0.6 }}>{new Date(o.created_at).toLocaleTimeString("zh-CN")}</span>
            </div>
          ))}
          {(state?.recent_orders ?? []).length === 0 ? <div style={{ opacity: 0.5 }}>暂无订单</div> : null}
        </div>
        <div style={card}>
          <div style={{ ...label, marginBottom: 12 }}>实时事件流</div>
          <div style={{ maxHeight: 360, overflowY: "auto" }}>
            {recentEvents.map((e) => (
              <div key={String(e.event_id)} style={{ padding: "4px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", fontFamily: "monospace", fontSize: 12 }}>
                <span style={{ color: "#f0c060" }}>{e.type}</span>
                <span style={{ marginLeft: 8, opacity: 0.6 }}>{new Date(e.created_at).toLocaleTimeString("zh-CN")}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
