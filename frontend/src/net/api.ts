// Thin fetch wrappers for the FastAPI backend. Backend contract is read-only
// here; do not change event structure, roles, or actions server-side.
const env = (import.meta as unknown as {
  env: { DEV?: boolean; VITE_API_BASE_URL?: string };
}).env;
const base = env?.VITE_API_BASE_URL ?? (env?.DEV ? "http://localhost:8000" : "");

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly detail?: unknown;

  constructor(message: string, status: number, code?: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" ? (value as Record<string, unknown>) : null;

async function responseError(res: Response, path: string): Promise<ApiError> {
  const payload = await res.json().catch(() => null);
  const body = asRecord(payload);
  const detail = body?.detail;
  const detailBody = asRecord(detail);
  const code =
    (typeof body?.code === "string" ? body.code : undefined) ??
    (typeof detailBody?.code === "string" ? detailBody.code : undefined) ??
    (typeof detail === "string" && /^[a-z0-9_]+$/i.test(detail) ? detail : undefined);
  const message =
    (typeof detailBody?.message === "string" ? detailBody.message : undefined) ??
    (typeof detail === "string" ? detail : undefined) ??
    (typeof body?.message === "string" ? body.message : undefined) ??
    `${path} -> ${res.status}`;
  return new ApiError(message, res.status, code, detail ?? payload);
}

export function hasApiErrorCode(error: unknown, code: string): boolean {
  if (error instanceof ApiError && error.code === code) return true;
  return error instanceof Error && error.message.toLowerCase().includes(code.toLowerCase());
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${base}${path}`, { credentials: "include" });
  if (!res.ok) throw await responseError(res, path);
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
    throw await responseError(res, path);
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
    throw await responseError(res, path);
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
  code?: string;
  requires_login?: boolean;
  login_required?: boolean;
  checkout_id?: string;
};
export const sendChat = (userId: number, message: string) =>
  postJson<ChatResponse>("/chat", { user_id: userId, message });

// 3D editor layout (server-side persistence). items is FurnitureItem[]; kept
// loosely typed here to avoid a types -> net import cycle.
export type OfficeLayoutResponse = {
  items: unknown[];
  namespace: string;
  updated_at?: string | null;
  version?: number | null;
};
export const getOfficeLayout = () => getJson<OfficeLayoutResponse>("/api/office/layout");
export const saveOfficeLayout = (items: unknown[], version?: number | null) =>
  putJson<{ ok: boolean; namespace: string; version: number }>("/api/office/layout", {
    items,
    ...(version !== undefined ? { version } : {}),
  });

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

// --- 咨询消息流（监控大屏） ---
export type ConsultFeedMessage = {
  account_id: number;
  role: string;       // "user" | "assistant"
  content: string;    // 消息内容（截断 200 字）
  timestamp: string;
};

export const getConsultFeed = (limit = 20) =>
  getJson<{ messages: ConsultFeedMessage[]; total: number }>(`/admin/consult-feed?limit=${limit}`);

// --- 需求榜单 + 认领任务 ---
export type Demand = {
  demand_id: number;
  title: string;
  description: string;
  category: string;
  reward_credits: number;
  status: string; // "open" | "claimed" | "done"
  creator_id: number;
  creator_name: string | null;
  claimer_id: number | null;
  claimer_name: string | null;
  created_at: string | null;
  claimed_at: string | null;
  completed_at: string | null;
};

export type DemandFeedItem = Demand & {
  latest_action: string; // "created" | "claimed" | "completed"
  action_time: string | null;
};

export const listDemands = (status?: string) =>
  getJson<{ demands: Demand[]; total: number }>(`/api/demands${status ? `?status=${status}` : ""}`);

export const createDemand = (body: { title: string; description?: string; category?: string; reward_credits?: number }) =>
  postJson<Demand>("/api/demands", body);

export const claimDemand = (demandId: number) =>
  postJson<Demand>(`/api/demands/${demandId}/claim`, {});

export const completeDemand = (demandId: number) =>
  postJson<Demand>(`/api/demands/${demandId}/complete`, {});

export const getDemandFeed = (limit = 20) =>
  getJson<{ demands: DemandFeedItem[]; total: number }>(`/admin/demand-feed?limit=${limit}`);


// --- 访客社交 ---
export type OnlineVisitor = {
  agent_id: number;
  display_name: string;
  user_id: number | null;
  joined_at: string;
};

export type VisitorChatMessage = {
  message_id?: string | number;
  client_message_id?: string;
  user_id: number | null;
  display_name: string;
  message: string;
  created_at?: string;
  delivery_status?: "sending" | "sent" | "failed";
};

export type VisitorChatSendResponse = {
  ok: boolean;
  message?: VisitorChatMessage;
  message_id?: string | number;
  client_message_id?: string;
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
  getJson<OnlineVisitorsResponse>("/api/online-visitors");

export const getVisitorChatHistory = (limit = 50) =>
  getJson<VisitorChatHistoryResponse>(`/api/visitor-chat/history?limit=${limit}`);

export const sendVisitorChat = (
  userId: number,
  displayName: string,
  message: string,
  clientMessageId?: string,
) =>
  postJson<VisitorChatSendResponse>('/api/visitor-chat', {
    user_id: userId,
    display_name: displayName,
    message,
    ...(clientMessageId ? { client_message_id: clientMessageId } : {}),
  });

export const getTodayTopics = () =>
  getJson<TodayTopicsResponse>("/api/today-topics");
