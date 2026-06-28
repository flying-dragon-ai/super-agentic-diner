// Thin fetch wrappers for the FastAPI backend. Backend contract is read-only
// here; do not change event structure, roles, or actions server-side.
const base = (import.meta as unknown as { env: { DEV?: boolean } }).env?.DEV
  ? "http://localhost:8000"
  : "";

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${base}${path}`, { credentials: "include" });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return (await res.json()) as T;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail?.detail || `${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function putJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail?.detail || `${path} -> ${res.status}`);
  }
  return (await res.json()) as T;
}

export type VisEvent = {
  event_id: string | number;
  type: string;
  agent_id: number | null;
  payload: Record<string, unknown>;
  correlation_id: string | null;
  created_at: string;
};

// Lean agent descriptor embedded in scene.snapshot.payload.agents.
// Backend emits snake_case; this mirrors the staff/customer snapshot fields.
export type SnapshotAgent = {
  agent_id: number;
  tool_name?: string;
  display_name: string;
  role_type: string;
  sprite_seed: number;
  status?: string;
};

export const listEvents = (limit = 50) => getJson<VisEvent[]>(`/visualization/events?limit=${limit}`);
export const getRestaurantState = () => getJson<unknown>("/admin/restaurant-state");

// --- 聊天点单（/chat，匿名 user_id）---
// 匿名 web 顾客的稳定 user_id：localStorage 一次生成复用，让同一浏览器始终
// 对应同一个顾客 agent（3D 人偶跨会话稳定）。900000-999999 区间避开 seed user_id。
const ANON_UID_KEY = "coffee_anon_user_id";
export function getAnonUserId(): number {
  try {
    let raw = localStorage.getItem(ANON_UID_KEY);
    if (!raw) {
      raw = String(900000 + Math.floor(Math.random() * 99999));
      localStorage.setItem(ANON_UID_KEY, raw);
    }
    return Number(raw);
  } catch {
    // localStorage 不可用（隐私模式）→ 每次会话随机
    return 900000 + Math.floor(Math.random() * 99999);
  }
}

export type ChatProduct = {
  name: string;
  price: number;
  tags?: string;
  category?: string;
  description?: string;
  image?: string;
  stock?: number;
};

export type ChatResponse = {
  reply: string;
  order_id?: number;
  products?: ChatProduct[];
};
export const sendChat = (userId: number, message: string) =>
  postJson<ChatResponse>("/chat", { user_id: userId, message });

// 3D editor layout (server-side persistence). items is FurnitureItem[]; kept
// loosely typed here to avoid a types -> net import cycle.
export type OfficeLayoutResponse = { items: unknown[]; namespace: string };
export const getOfficeLayout = () => getJson<OfficeLayoutResponse>("/api/office/layout");
export const saveOfficeLayout = (items: unknown[]) =>
  putJson<{ ok: boolean; namespace: string }>("/api/office/layout", { items });

export { base };

// --- 访客分析 / 流失分析（大屏专用） ---
export type VisitorAnalytics = {
  total_visitors: number;
  ordered_visitors: number;
  churned_visitors: number;
  conversion_rate: number;
  intent_distribution: Record<string, number>;
  visitors: {
    user_id: number;
    first_message?: string;
    last_message?: string;
    message_count: number;
    primary_intent: string;
    ordered: number;
    order_id?: number;
    churn_reason?: string;
    ai_insight?: string;
    visit_time: string;
  }[];
};
export const getVisitorAnalytics = () => getJson<VisitorAnalytics>("/admin/visitor-analytics");

export type ChurnAnalysis = {
  today_churned: number;
  today_churn_details: {
    user_id: number;
    message_count: number;
    primary_intent: string;
    last_message?: string;
    churn_reason?: string;
    ai_insight?: string;
  }[];
  churn_patterns: Record<string, number>;
  total_analyzed: number;
};
export const getChurnAnalysis = () => getJson<ChurnAnalysis>("/admin/churn-analysis");

// --- 访客社交 ---
export type OnlineVisitor = {
  agent_id: number;
  display_name: string;
  user_id: number | null;
  joined_at: string;
};

export type VisitorChatMessage = {
  user_id: number | null;
  display_name: string;
  message: string;
  created_at?: string;
};

export type OnlineVisitorsResponse = {
  count: number;
  visitors: OnlineVisitor[];
};

export type TodayTopic = {
  label: string;
  type: string;
  count: number;
  heat: number;
  rank: number;
};

export type TodayTopicsResponse = {
  topics: TodayTopic[];
  total_orders_today: number;
  total_chats_today: number;
  updated_at: string;
};

export type VisitorChatHistoryResponse = {
  messages: VisitorChatMessage[];
  total: number;
};

export const getOnlineVisitors = () =>
  getJson<OnlineVisitorsResponse>("/admin/online-visitors");

export const getVisitorChatHistory = (limit = 50) =>
  getJson<VisitorChatHistoryResponse>(`/admin/visitor-chat?limit=${limit}`);

export const sendVisitorChat = (userId: number, displayName: string, message: string) =>
  postJson<{ ok: boolean }>('/api/visitor-chat', {
    user_id: userId,
    display_name: displayName,
    message,
  });

export const getTodayTopics = () =>
  getJson<TodayTopicsResponse>("/admin/today-topics");
