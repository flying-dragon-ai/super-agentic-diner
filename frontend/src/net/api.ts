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

export type VisEvent = {
  event_id: string | number;
  type: string;
  agent_id: number | null;
  payload: Record<string, unknown>;
  correlation_id: string | null;
  created_at: string;
};

export const listEvents = (limit = 50) => getJson<VisEvent[]>(`/visualization/events?limit=${limit}`);
export const getRestaurantState = () => getJson<unknown>("/admin/restaurant-state");
export { base };
