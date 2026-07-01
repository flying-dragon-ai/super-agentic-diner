// Big-screen dashboard. Aggregates /admin/restaurant-state (today's order count
// + amount, source split, recent orders/events, active agents/consumers) and a
// recent event feed, on a dark monitoring-friendly layout.
// Also shows visitor analytics (conversion rate, intent distribution) and
// churn analysis (AI-powered reasons for why visitors didn't order).
import { useEffect, useState } from "react";
import { getRestaurantState, listEvents, getVisitorAnalytics, getChurnAnalysis, type VisEvent, type VisitorAnalytics, type ChurnAnalysis } from "../net/api";

type State = {
  summary?: {
    today_order_count?: number;
    today_amount?: number;
    source_stats?: { source_type: string; count: number; amount: number }[];
    active_agent_count?: number;
    active_staff_count?: number;
    active_customer_agent_count?: number;
    active_consumer_count?: number;
  };
  today?: { order_count?: number; total_amount?: number; active_agent_count?: number; active_consumer_count?: number };
  recent_orders?: { order_id: number; coffee_name: string; amount: number; status: number; source_type: string; payment_status?: string; created_at: string }[];
  recent_events?: VisEvent[];
  agents?: { display_name?: string; role_type?: string; status?: string }[];
  consumers?: { display_name?: string; status?: string }[];
};

const card: React.CSSProperties = { background: "rgba(14,22,34,0.9)", border: "1px solid rgba(80,130,200,0.18)", borderRadius: 10, padding: 18 };
const label: React.CSSProperties = { color: "#7fa6d8", fontSize: 12, letterSpacing: 2, textTransform: "uppercase" };
const num: React.CSSProperties = { color: "#e8dfc0", fontSize: 34, fontWeight: 700, fontFamily: "monospace" };
const smallNum: React.CSSProperties = { color: "#e8dfc0", fontSize: 22, fontWeight: 700, fontFamily: "monospace" };

const SOURCE_TEXT: Record<string, string> = {
  web_dialog: "网页点单",
  skill: "A2A 点单",
  unknown: "未知来源",
};

const EVENT_TEXT: Record<string, string> = {
  "message.received": "收到顾客消息",
  "order.intent_detected": "已识别点单需求",
  "order.pending_confirmation": "等待顾客确认订单",
  "order.payment_required": "等待顾客确认支付",
  "order.payment_failed": "支付未完成",
  "order.paid": "支付完成，订单已确认",
  "order.failed": "订单处理失败",
  "order.reply": "店长已回复顾客",
  "restaurant.customer_entered": "顾客进入Crossroads Agent Café",
  "restaurant.order_ticketed": "已生成点单小票",
  "restaurant.order_confirming": "正在确认订单内容",
  "restaurant.payment_requested": "已向顾客发起支付",
  "restaurant.payment_processing": "正在处理支付",
  "restaurant.payment_completed": "支付完成，准备制作",
  "restaurant.payment_failed": "支付失败，等待重试",
  "restaurant.preparation_progress": "咖啡正在制作中",
  "restaurant.order_ready": "咖啡已制作完成",
  "restaurant.order_delivered": "咖啡已送达顾客",
  "restaurant.customer_reviewed": "顾客已完成评价",
  "restaurant.customer_left": "顾客离开Crossroads Agent Café",
  "restaurant.order_failed": "订单流程异常",
  "agent.registered": "员工或顾客已进入Crossroads Agent Café",
  "agent.action": "员工正在处理订单",
  "agent.manager.intent": "店长 Agent 已判断意图",
  "agent.recommender.suggesting": "推荐 Agent 正在生成建议",
  "agent.recommender.suggested": "推荐 Agent 已给出建议",
  "agent.reviewer.reviewing": "复盘 Agent 正在评估结果",
  "agent.reviewer.reviewed": "复盘 Agent 已完成评估",
  "agent.experience.learned": "经验 Agent 已沉淀经验",
  "agent.experience.applied": "经验 Agent 已应用历史经验",
};

const AGENT_ACTION_TEXT: Record<string, string> = {
  enter_scene: "员工回到岗位",
  walk_to_counter: "服务员前往点单台",
  take_order: "收银员正在接单",
  prepare_coffee: "咖啡师开始制作",
  deliver_order: "服务员正在送餐",
  show_message: "员工正在回复顾客",
  leave_scene: "员工离开Crossroads Agent Café",
};

const INTENT_TEXT: Record<string, string> = {
  order: "下单",
  recommend: "求推荐",
  chat: "闲聊",
  browse: "浏览",
};

const INTENT_COLOR: Record<string, string> = {
  order: "#4ade80",
  recommend: "#f0c060",
  chat: "#7fa6d8",
  browse: "#9ca3af",
};

function formatEvent(event: VisEvent) {
  if (event.type === "agent.action") {
    const actionType = typeof event.payload?.action_type === "string" ? event.payload.action_type : "";
    return AGENT_ACTION_TEXT[actionType] ?? EVENT_TEXT[event.type];
  }
  return EVENT_TEXT[event.type] ?? "Crossroads Agent Café状态已更新";
}

function sourceText(sourceType: string) {
  return SOURCE_TEXT[sourceType] ?? sourceType;
}

export default function Dashboard() {
  const [state, setState] = useState<State | null>(null);
  const [events, setEvents] = useState<VisEvent[]>([]);
  const [visitorData, setVisitorData] = useState<VisitorAnalytics | null>(null);
  const [churnData, setChurnData] = useState<ChurnAnalysis | null>(null);

  useEffect(() => {
    const load = () => {
      getRestaurantState().then((s) => setState(s as State)).catch(() => {});
      listEvents(30).then(setEvents).catch(() => {});
    };
    const loadVisitor = () => {
      getVisitorAnalytics().then(setVisitorData).catch(() => {});
      getChurnAnalysis().then(setChurnData).catch(() => {});
    };
    load();
    loadVisitor();
    const t = setInterval(load, 4000);
    const tv = setInterval(loadVisitor, 8000);
    return () => { clearInterval(t); clearInterval(tv); };
  }, []);

  const recentEvents = events.length ? events : (state?.recent_events ?? []);
  const summary = state?.summary;
  const todayOrderCount = summary?.today_order_count ?? state?.today?.order_count;
  const todayAmount = summary?.today_amount ?? state?.today?.total_amount;
  const activeStaffCount =
    summary?.active_staff_count ??
    state?.agents?.filter((agent) => agent.role_type && agent.role_type !== "customer").length ??
    state?.today?.active_agent_count;
  const activeConsumerCount =
    summary?.active_consumer_count ??
    state?.consumers?.length ??
    state?.today?.active_consumer_count;

  const totalVisitors = visitorData?.total_visitors ?? 0;
  const orderedVisitors = visitorData?.ordered_visitors ?? 0;
  const churnedVisitors = visitorData?.churned_visitors ?? 0;
  const conversionRate = visitorData?.conversion_rate ?? 0;

  return (
    <div style={{ width: "100vw", minHeight: "100vh", background: "#080c12", color: "#dfe8f5", fontFamily: "system-ui, sans-serif", padding: 24, boxSizing: "border-box", overflow: "auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 24, letterSpacing: 2 }}>Crossroads Agent Café · 实时监控大屏</h1>
        <span style={{ color: "#7fa6d8", fontSize: 13 }}>{new Date().toLocaleString("zh-CN")}</span>
      </div>

      {/* Row 1: Core stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 12, marginBottom: 16 }}>
        <div style={card}><div style={label}>今日订单</div><div style={num}>{todayOrderCount ?? "—"}</div></div>
        <div style={card}><div style={label}>今日金额</div><div style={num}>¥{todayAmount != null ? Number(todayAmount).toFixed(2) : "—"}</div></div>
        <div style={card}><div style={label}>今日访客</div><div style={{ ...num, color: "#7fa6d8" }}>{totalVisitors}</div></div>
        <div style={card}><div style={label}>转化率</div><div style={{ ...num, color: conversionRate >= 50 ? "#4ade80" : conversionRate > 0 ? "#f0c060" : "#9ca3af" }}>{conversionRate}%</div></div>
        <div style={card}><div style={label}>在线员工</div><div style={smallNum}>{activeStaffCount ?? "—"}</div></div>
        <div style={card}><div style={label}>活跃访客</div><div style={smallNum}>{activeConsumerCount ?? "—"}</div></div>
      </div>

      {/* Row 2: Visitor analytics + Churn analysis */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 16 }}>
        {/* Visitor conversion funnel */}
        <div style={card}>
          <div style={{ ...label, marginBottom: 12 }}>访客转化漏斗</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ color: "#7fa6d8", fontSize: 13 }}>总访客</span>
              <span style={{ color: "#e8dfc0", fontSize: 18, fontWeight: 700 }}>{totalVisitors}</span>
            </div>
            <div style={{ height: 6, background: "rgba(127,166,216,0.15)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{ width: "100%", height: "100%", background: "#7fa6d8", borderRadius: 3 }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
              <span style={{ color: "#4ade80", fontSize: 13 }}>已下单</span>
              <span style={{ color: "#e8dfc0", fontSize: 18, fontWeight: 700 }}>{orderedVisitors}</span>
            </div>
            <div style={{ height: 6, background: "rgba(74,222,128,0.15)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{ width: `${totalVisitors > 0 ? (orderedVisitors / totalVisitors * 100) : 0}%`, height: "100%", background: "#4ade80", borderRadius: 3 }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
              <span style={{ color: "#f87171", fontSize: 13 }}>未下单（流失）</span>
              <span style={{ color: "#e8dfc0", fontSize: 18, fontWeight: 700 }}>{churnedVisitors}</span>
            </div>
            <div style={{ height: 6, background: "rgba(248,113,113,0.15)", borderRadius: 3, overflow: "hidden" }}>
              <div style={{ width: `${totalVisitors > 0 ? (churnedVisitors / totalVisitors * 100) : 0}%`, height: "100%", background: "#f87171", borderRadius: 3 }} />
            </div>
          </div>
        </div>

        {/* Intent distribution */}
        <div style={card}>
          <div style={{ ...label, marginBottom: 12 }}>访客意图分布</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {visitorData?.intent_distribution && Object.entries(visitorData.intent_distribution).map(([intent, count]) => {
              const pct = totalVisitors > 0 ? (count / totalVisitors * 100) : 0;
              const color = INTENT_COLOR[intent] ?? "#9ca3af";
              return (
                <div key={intent}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                    <span style={{ color, fontSize: 12 }}>{INTENT_TEXT[intent] ?? intent}</span>
                    <span style={{ color: "#e8dfc0", fontSize: 12 }}>{count} ({pct.toFixed(0)}%)</span>
                  </div>
                  <div style={{ height: 8, background: "rgba(255,255,255,0.05)", borderRadius: 4, overflow: "hidden" }}>
                    <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 4, transition: "width 0.5s" }} />
                  </div>
                </div>
              );
            })}
            {(!visitorData?.intent_distribution || Object.keys(visitorData.intent_distribution).length === 0) && (
              <div style={{ opacity: 0.5 }}>暂无访客数据</div>
            )}
          </div>
        </div>

        {/* Churn analysis */}
        <div style={card}>
          <div style={{ ...label, marginBottom: 12 }}>流失原因分析 <span style={{ color: "#f0c060", fontSize: 10, marginLeft: 4 }}>AI 自进化</span></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {churnData?.churn_patterns && Object.entries(churnData.churn_patterns).sort((a, b) => b[1] - a[1]).map(([cat, count]) => (
              <div key={cat} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 8px", background: "rgba(248,113,113,0.06)", borderRadius: 6 }}>
                <span style={{ color: "#f87171", fontSize: 12 }}>{cat}</span>
                <span style={{ color: "#e8dfc0", fontSize: 13, fontWeight: 700 }}>{count}</span>
              </div>
            ))}
            {(!churnData?.churn_patterns || Object.keys(churnData.churn_patterns).length === 0) && (
              <div style={{ opacity: 0.5, fontSize: 12 }}>
                {churnData?.today_churned === 0 ? "今日暂无流失访客" : "AI 正在分析流失原因..."}
              </div>
            )}
            {churnData && churnData.total_analyzed > 0 && (
              <div style={{ marginTop: 4, color: "#7fa6d8", fontSize: 11 }}>
                已分析 {churnData.total_analyzed} 条流失记录
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Row 3: Visitor list + Recent orders + Events */}
      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1.4fr 1.2fr", gap: 16, marginBottom: 16 }}>
        {/* Today's visitors */}
        <div style={card}>
          <div style={{ ...label, marginBottom: 12 }}>今日访客列表</div>
          <div style={{ maxHeight: 280, overflowY: "auto" }}>
            {(visitorData?.visitors ?? []).map((v) => (
              <div key={v.user_id} style={{ padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", fontSize: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ color: "#e8dfc0" }}>#{v.user_id} · {v.visit_time}</span>
                  <span style={{
                    padding: "1px 6px",
                    borderRadius: 4,
                    fontSize: 10,
                    color: v.ordered ? "#4ade80" : (INTENT_COLOR[v.primary_intent] ?? "#9ca3af"),
                    border: `1px solid ${v.ordered ? "rgba(74,222,128,0.3)" : "rgba(255,255,255,0.1)"}`,
                  }}>
                    {v.ordered ? "已下单" : (INTENT_TEXT[v.primary_intent] ?? v.primary_intent)}
                  </span>
                </div>
                <div style={{ color: "#9fb6d8", fontSize: 11, marginTop: 2 }}>
                  {v.last_message ? `"${v.last_message.slice(0, 40)}${v.last_message.length > 40 ? "..." : ""}"` : ""} · {v.message_count} 条消息
                </div>
                {v.churn_reason && !v.ordered && (
                  <div style={{ color: "#f87171", fontSize: 11, marginTop: 2 }}>流失: {v.churn_reason}</div>
                )}
              </div>
            ))}
            {(!visitorData?.visitors || visitorData.visitors.length === 0) && (
              <div style={{ opacity: 0.5 }}>暂无访客</div>
            )}
          </div>
        </div>

        {/* Recent orders */}
        <div style={card}>
          <div style={{ ...label, marginBottom: 12 }}>最近订单</div>
          {(state?.recent_orders ?? []).map((o) => (
            <div key={o.order_id} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", fontFamily: "monospace", fontSize: 13 }}>
              <span style={{ color: "#e8dfc0" }}>{o.coffee_name}</span>
              <span style={{ color: "#9fb6d8" }}>{sourceText(o.source_type)}</span>
              <span style={{ color: "#f0c060" }}>¥{Number(o.amount).toFixed(2)}</span>
              <span style={{ opacity: 0.6 }}>{new Date(o.created_at).toLocaleTimeString("zh-CN")}</span>
            </div>
          ))}
          {(state?.recent_orders ?? []).length === 0 ? <div style={{ opacity: 0.5 }}>暂无订单</div> : null}
        </div>

        {/* Real-time events */}
        <div style={card}>
          <div style={{ ...label, marginBottom: 12 }}>实时事件流</div>
          <div style={{ maxHeight: 280, overflowY: "auto" }}>
            {recentEvents.map((e) => (
              <div key={String(e.event_id)} style={{ padding: "4px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", fontFamily: "monospace", fontSize: 12 }}>
                <span style={{ color: "#f0c060" }}>{formatEvent(e)}</span>
                <span style={{ marginLeft: 8, opacity: 0.6 }}>{new Date(e.created_at).toLocaleTimeString("zh-CN")}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
