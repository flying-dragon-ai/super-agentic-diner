// WebSocket client for /ws/visualization. On connect the server sends a
// scene.snapshot (recent events); afterwards single events are broadcast.
// Events are handed to the caller via onEvent, including snapshot replay.
//
// Enhanced with: exponential backoff reconnect, heartbeat keepalive,
// message queue for offline buffering, and connection quality reporting.
import type { SnapshotAgent, VisEvent } from "./api";

const wsUrl = () => {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const env = (import.meta as unknown as {
    env: { DEV?: boolean; VITE_VISUALIZATION_WS_URL?: string };
  }).env;
  const explicit = env?.VITE_VISUALIZATION_WS_URL?.trim();
  if (explicit) return explicit;
  if (env?.DEV) return `${proto}//${window.location.hostname || "localhost"}:8000/ws/visualization`;
  return `${proto}//${window.location.host}/ws/visualization`;
};

export type ConnectionQuality = "excellent" | "good" | "poor" | "disconnected";

export type SocketHandle = {
  close: () => void;
  send: (data: unknown) => void;
  getQuality: () => ConnectionQuality;
};

// Heartbeat: send ping every 15s, expect any response within 40s or reconnect.
const HEARTBEAT_INTERVAL = 15_000;
const HEARTBEAT_TIMEOUT = 40_000;
// Max backoff: 2s → 4s → 8s → 16s → 30s cap.
const MAX_BACKOFF = 30_000;
// Max queued messages while offline.
const MAX_QUEUE = 50;

export function connectVisualization(opts: {
  onEvent: (event: VisEvent) => void;
  onSnapshot?: (agents: SnapshotAgent[]) => void;
  onStatus?: (status: "connecting" | "open" | "closed") => void;
  onQuality?: (quality: ConnectionQuality) => void;
}): SocketHandle {
  let closed = false;
  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  let heartbeatTimeoutTimer: ReturnType<typeof setTimeout> | null = null;
  let backoff = 2000;
  let lastMessageTime = performance.now();
  let quality: ConnectionQuality = "disconnected";
  const messageQueue: string[] = [];

  const reportQuality = (q: ConnectionQuality) => {
    if (q === quality) return;
    quality = q;
    opts.onQuality?.(q);
  };

  const clearTimers = () => {
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
    if (heartbeatTimeoutTimer) { clearTimeout(heartbeatTimeoutTimer); heartbeatTimeoutTimer = null; }
  };

  const startHeartbeat = () => {
    clearTimers();
    heartbeatTimer = setInterval(() => {
      if (ws?.readyState === WebSocket.OPEN) {
        // Send a lightweight ping (server ignores unknown messages gracefully).
        try {
          ws.send(JSON.stringify({ type: "ping" }));
        } catch {
          // Ignore send errors — heartbeat timeout will catch dead connections.
        }
      }
      // Check for missed heartbeats.
      const sinceLast = performance.now() - lastMessageTime;
      if (sinceLast > HEARTBEAT_TIMEOUT) {
        // Connection is stale — force reconnect.
        try { ws?.close(); } catch { /* ignore */ }
      }
    }, HEARTBEAT_INTERVAL);
  };

  const flushQueue = () => {
    if (ws?.readyState !== WebSocket.OPEN) return;
    while (messageQueue.length > 0) {
      const msg = messageQueue.shift()!;
      try { ws.send(msg); } catch { break; }
    }
  };

  const open = () => {
    if (closed) return;
    opts.onStatus?.("connecting");
    reportQuality("disconnected");

    try {
      ws = new WebSocket(wsUrl());
    } catch {
      // URL or network failure — schedule retry.
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      opts.onStatus?.("open");
      reportQuality("excellent");
      backoff = 2000; // Reset backoff on successful connect.
      lastMessageTime = performance.now();
      startHeartbeat();
      flushQueue();
    };

    ws.onclose = (event) => {
      opts.onStatus?.("closed");
      reportQuality("disconnected");
      clearTimers();
      if (closed) return;
      // Only reconnect if it wasn't a clean close (code 1000).
      if (event.code !== 1000) {
        scheduleReconnect();
      }
    };

    ws.onerror = () => {
      reportQuality("poor");
      // Don't close immediately — let onclose handle reconnect.
      try { ws?.close(); } catch { /* ignore */ }
    };

    ws.onmessage = (msg) => {
      lastMessageTime = performance.now();
      // Update quality based on message latency (rough estimate).
      const sinceLast = performance.now() - lastMessageTime;
      if (sinceLast < 500) reportQuality("excellent");
      else if (sinceLast < 2000) reportQuality("good");

      let data: unknown;
      try {
        data = JSON.parse(msg.data);
      } catch {
        return;
      }
      // Ignore pong messages (heartbeat responses).
      if ((data as { type?: string })?.type === "pong") return;

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

  const scheduleReconnect = () => {
    if (closed) return;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      open();
    }, backoff);
    // Exponential backoff with jitter.
    backoff = Math.min(MAX_BACKOFF, backoff * 2 + Math.random() * 500);
  };

  const send = (data: unknown) => {
    const str = typeof data === "string" ? data : JSON.stringify(data);
    if (ws?.readyState === WebSocket.OPEN) {
      try { ws.send(str); } catch { /* ignore */ }
    } else {
      // Queue for later delivery.
      if (messageQueue.length < MAX_QUEUE) messageQueue.push(str);
    }
  };

  const getQuality = () => quality;

  open();
  return {
    close: () => {
      closed = true;
      clearTimers();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      try { ws?.close(1000, "client closed"); } catch { /* ignore */ }
    },
    send,
    getQuality,
  };
}
