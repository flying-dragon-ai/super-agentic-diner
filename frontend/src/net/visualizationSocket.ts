// WebSocket client for /ws/visualization. On connect the server sends a
// scene.snapshot (recent events); afterwards single events are broadcast.
// Events are handed to the caller via onEvent, including snapshot replay.
import type { SnapshotAgent, VisEvent } from "./api";

const wsUrl = () => {
  const dev = (import.meta as unknown as { env: { DEV?: boolean } }).env?.DEV;
  if (dev) return "ws://localhost:8000/ws/visualization";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/visualization`;
};

export type SocketHandle = { close: () => void };

export function connectVisualization(opts: {
  onEvent: (event: VisEvent) => void;
  onSnapshot?: (agents: SnapshotAgent[]) => void;
  onStatus?: (status: "connecting" | "open" | "closed") => void;
}): SocketHandle {
  let closed = false;
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  const open = () => {
    opts.onStatus?.("connecting");
    ws = new WebSocket(wsUrl());
    ws.onopen = () => opts.onStatus?.("open");
    ws.onclose = () => {
      opts.onStatus?.("closed");
      if (closed) return;
      reconnectTimer = setTimeout(open, 2000);
    };
    ws.onerror = () => ws?.close();
    ws.onmessage = (msg) => {
      let data: unknown;
      try {
        data = JSON.parse(msg.data);
      } catch {
        return;
      }
      const message = data as {
        type?: string;
        payload?: { events?: VisEvent[]; agents?: SnapshotAgent[] };
      };
      if (message?.type === "scene.snapshot") {
        opts.onSnapshot?.(Array.isArray(message.payload?.agents) ? message.payload!.agents! : []);
        if (Array.isArray(message.payload?.events)) {
          for (const ev of message.payload!.events!) opts.onEvent(ev);
        }
      } else if (message && typeof message === "object" && "type" in message) {
        opts.onEvent(message as VisEvent);
      }
    };
  };

  open();
  return { close: () => { closed = true; if (reconnectTimer) clearTimeout(reconnectTimer); ws?.close(); } };
}
