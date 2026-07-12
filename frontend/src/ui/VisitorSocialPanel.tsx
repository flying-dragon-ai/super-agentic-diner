// Visitor social panel: visitor chat + the scene's single AI assistant entry.
// Tab 1: real-time visitor-to-visitor text chat (WebSocket + REST hybrid).
// Tab 2: AI bot interaction (uses /chat API).
// Tab 3: online visitor roster with invite-link.
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import {
  getAnonUserId,
  hasApiErrorCode,
  getOnlineVisitors,
  getVisitorChatHistory,
  sendVisitorChat,
  sendChat,
  type OnlineVisitor,
  type VisitorChatMessage,
  type ChatProduct,
} from "../net/api";

type Props = {
  registerChatConsumer?: (handler: (msg: VisitorChatMessage) => void) => void | (() => void);
};

// AI bot message type (reply can include product cards).
type BotMsg = {
  role: "user" | "bot";
  text: string;
  products?: ChatProduct[];
  loginRequired?: boolean;
  checkoutId?: string;
};

const ANON_NAME_KEY = "coffee_visitor_display_name";

function getDisplayName(): string {
  try {
    const stored = localStorage.getItem(ANON_NAME_KEY);
    if (stored) return stored;
  } catch {
    // localStorage not available
  }
  const names = ["\u5496\u5561\u7231\u597d\u8005", "\u62ff\u94c1\u661f\u4eba", "\u7f8e\u5f0f\u5148\u950b", "\u6469\u5361\u8fbe\u4eba", "\u5361\u5e03\u5947\u8bfa\u4e4b\u53cb", "\u6d53\u7f29\u4fe1\u5f92"];
  const name = names[Math.floor(Math.random() * names.length)];
  try {
    localStorage.setItem(ANON_NAME_KEY, name);
  } catch {
    // ignore
  }
  return name;
}

function createClientMessageId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `visitor-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

const messageIdentity = (message: VisitorChatMessage): string | null =>
  message.message_id !== undefined && message.message_id !== null
    ? String(message.message_id)
    : message.client_message_id ?? null;

function legacyDeliveryDistance(
  left: VisitorChatMessage,
  right: VisitorChatMessage,
): number | null {
  if (
    left.user_id !== right.user_id ||
    left.display_name !== right.display_name ||
    left.message !== right.message
  ) return null;
  const hasOptimisticDelivery = Boolean(
    left.client_message_id ||
    right.client_message_id ||
    left.delivery_status ||
    right.delivery_status,
  );
  if (left.created_at && right.created_at) {
    const delta = Math.abs(Date.parse(left.created_at) - Date.parse(right.created_at));
    if (!Number.isFinite(delta)) return null;
    if (hasOptimisticDelivery && delta <= 30_000) return delta;
    if (!hasOptimisticDelivery && delta === 0) return 0;
  }
  return null;
}

function upsertVisitorMessage(
  previous: VisitorChatMessage[],
  incoming: VisitorChatMessage,
): VisitorChatMessage[] {
  const incomingIdentity = messageIdentity(incoming);
  let index = incomingIdentity
    ? previous.findIndex((message) =>
        (message.message_id !== undefined && String(message.message_id) === incomingIdentity) ||
        message.client_message_id === incomingIdentity)
    : -1;

  if (index < 0 && incoming.client_message_id) {
    index = previous.findIndex((message) => message.client_message_id === incoming.client_message_id);
  }
  // Legacy backend compatibility: old visitor.chat events have no message_id.
  // Reconcile them with the recent optimistic delivery instead of appending a
  // duplicate. Repeated user messages remain distinct because each optimistic
  // send has its own client_message_id and only a recent matching delivery wins.
  if (index < 0 && !incoming.client_message_id) {
    let closestDistance = Number.POSITIVE_INFINITY;
    previous.forEach((message, candidateIndex) => {
      const distance = legacyDeliveryDistance(message, incoming);
      if (distance !== null && distance <= closestDistance) {
        closestDistance = distance;
        index = candidateIndex;
      }
    });
  }

  if (index >= 0) {
    const next = [...previous];
    next[index] = {
      ...previous[index],
      ...incoming,
      client_message_id:
        incoming.client_message_id ?? previous[index].client_message_id,
      delivery_status: incoming.delivery_status ?? "sent",
    };
    return next.slice(-100);
  }
  return [...previous.slice(-99), incoming];
}

const chatResponseNeedsLogin = (response: {
  code?: string;
  requires_login?: boolean;
  login_required?: boolean;
}) =>
  response.code === "login_required" ||
  response.requires_login === true ||
  response.login_required === true;

export function VisitorSocialPanel({ registerChatConsumer }: Props) {
  const { account } = useAuth();
  const navigate = useNavigate();
  // --- Visitor chat state ---
  const [messages, setMessages] = useState<VisitorChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  // --- AI bot chat state ---
  const [botMessages, setBotMessages] = useState<BotMsg[]>([]);
  const [botInput, setBotInput] = useState("");
  const [botBusy, setBotBusy] = useState(false);
  const botBusyRef = useRef(false);
  const botScrollRef = useRef<HTMLDivElement>(null);

  // --- Shared state ---
  const [onlineVisitors, setOnlineVisitors] = useState<OnlineVisitor[]>([]);
  const [expanded, setExpanded] = useState(true);
  const [tab, setTab] = useState<"chat" | "bot" | "visitors">("chat");
  const [anonymousDisplayName] = useState(getDisplayName);
  const anonymousUserId = useRef(getAnonUserId());
  const activeUserId = account?.user_id ?? anonymousUserId.current;
  const activeDisplayName = account?.nickname || account?.username || anonymousDisplayName;
  const scrollRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load chat history on mount.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getVisitorChatHistory(50);
        if (!cancelled && data.messages) {
          setMessages(data.messages.reduce(upsertVisitorMessage, [] as VisitorChatMessage[]));
        }
      } catch {
        // Backend might not be ready; silently ignore.
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Poll online visitors every 10 seconds.
  useEffect(() => {
    const fetchVisitors = async () => {
      try {
        const data = await getOnlineVisitors();
        setOnlineVisitors(data.visitors ?? []);
      } catch {
        // ignore
      }
    };
    void fetchVisitors();
    pollRef.current = setInterval(fetchVisitors, 10_000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // Register consumer for real-time visitor.chat WebSocket events.
  useEffect(() => {
    if (!registerChatConsumer) return;
    const unregister = registerChatConsumer((msg: VisitorChatMessage) => {
      setMessages((prev) => upsertVisitorMessage(prev, { ...msg, delivery_status: "sent" }));
    });
    return typeof unregister === "function" ? unregister : undefined;
  }, [registerChatConsumer]);

  // Auto-scroll to bottom on new messages.
  useEffect(() => {
    if (scrollRef.current && expanded && tab === "chat") {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, expanded, tab]);

  // Auto-scroll bot chat.
  useEffect(() => {
    botScrollRef.current?.scrollTo({ top: botScrollRef.current.scrollHeight });
  }, [botMessages]);

  // --- Visitor chat handlers ---
  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || sending) return;
    setSending(true);
    const clientMessageId = createClientMessageId();
    const msg: VisitorChatMessage = {
      client_message_id: clientMessageId,
      user_id: activeUserId,
      display_name: activeDisplayName,
      message: trimmed,
      created_at: new Date().toISOString(),
      delivery_status: "sending",
    };
    setMessages((prev) => upsertVisitorMessage(prev, msg));
    setInput("");
    try {
      const response = await sendVisitorChat(
        activeUserId,
        activeDisplayName,
        trimmed,
        clientMessageId,
      );
      const canonicalMessage = response.message;
      if (canonicalMessage) {
        setMessages((prev) => upsertVisitorMessage(prev, {
          ...canonicalMessage,
          client_message_id: canonicalMessage.client_message_id ?? clientMessageId,
          delivery_status: "sent",
        }));
      } else {
        setMessages((prev) => prev.map((message) =>
          message.client_message_id === clientMessageId
            ? {
                ...message,
                message_id: response.message_id ?? message.message_id,
                client_message_id: response.client_message_id ?? clientMessageId,
                created_at: response.created_at ?? message.created_at,
                delivery_status: "sent",
              }
            : message));
      }
    } catch {
      setMessages((prev) => prev.map((message) =>
        message.client_message_id === clientMessageId
          ? { ...message, delivery_status: "failed" }
          : message));
    } finally {
      setSending(false);
    }
  }, [input, sending, activeUserId, activeDisplayName]);

  // --- AI bot handlers ---
  const sendBotPrompt = useCallback(async (text: string) => {
    if (!text || botBusyRef.current) return;
    botBusyRef.current = true;
    setBotMessages((m) => [...m, { role: "user", text }]);
    setBotBusy(true);
    try {
      const res = await sendChat(activeUserId, text);
      if (chatResponseNeedsLogin(res)) {
        setBotMessages((m) => [...m, {
          role: "bot",
          text: res.reply || "需要登录后才能确认并结算订单。",
          loginRequired: true,
          checkoutId: res.checkout_id,
        }]);
      } else {
        setBotMessages((m) => [...m, { role: "bot", text: res.reply, products: res.products }]);
      }
    } catch (e) {
      const loginRequired = hasApiErrorCode(e, "login_required");
      setBotMessages((m) => [...m, {
        role: "bot",
        text: loginRequired
          ? "需要登录后才能确认并结算订单。登录后可返回场景继续。"
          : `\u51fa\u9519\u4e86\uff1a${(e as Error).message}`,
        loginRequired,
      }]);
    } finally {
      botBusyRef.current = false;
      setBotBusy(false);
    }
  }, [activeUserId]);

  const handleBotSend = useCallback(async () => {
    const text = botInput.trim();
    if (!text || botBusy) return;
    setBotInput("");
    await sendBotPrompt(text);
  }, [botInput, botBusy, sendBotPrompt]);

  const handleBotKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void handleBotSend();
      }
    },
    [handleBotSend],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    },
    [handleSend],
  );

  // Quick prompts for the AI bot.
  const BOT_QUICK = [
    { label: "\u2615 \u770b\u83dc\u5355", prompt: "\u770b\u770b\u83dc\u5355" },
    { label: "\u2728 \u63a8\u8350", prompt: "\u63a8\u8350\u4e00\u676f\u5496\u5561" },
    { label: "\u2698\ufe0f \u70ed\u996e", prompt: "\u63a8\u8350\u4e00\u676f\u70ed\u996e" },
    { label: "\ud83e\uddca \u51b7\u996e", prompt: "\u6709\u6ca1\u6709\u9002\u5408\u51b0\u7740\u559d\u7684\u6e05\u723d\u51b7\u8403\uff1f" },
  ];

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        style={{
          position: "absolute",
          bottom: 12,
          left: 12,
          zIndex: 30,
          padding: "8px 16px",
          fontFamily: "monospace",
          fontSize: 12,
          cursor: "pointer",
          border: "1px solid rgba(255,255,255,0.2)",
          background: "rgba(8,12,20,0.85)",
          color: "#cfe0ff",
          borderRadius: 6,
        }}
      >
        {"\u{1F4AC} \u8bbf\u5ba2\u4ea4\u6d41"} ({onlineVisitors.length} {"\u5728\u7ebf"})
      </button>
    );
  }

  const panelStyle: React.CSSProperties = {
    position: "absolute",
    bottom: 12,
    left: 12,
    zIndex: 30,
    width: "min(320px, calc(100vw - 24px))",
    maxHeight: "min(420px, calc(100vh - 96px))",
    display: "flex",
    flexDirection: "column",
    background: "rgba(8,12,20,0.88)",
    backdropFilter: "blur(8px)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 8,
    overflow: "hidden",
    fontFamily: "monospace",
    fontSize: 12,
    color: "#cfe0ff",
  };

  const tabButtonStyle = (active: boolean): React.CSSProperties => ({
    flex: 1,
    padding: "8px 0",
    cursor: "pointer",
    border: "none",
    background: active ? "rgba(240,192,96,0.15)" : "transparent",
    color: active ? "#f0c060" : "#7a8aa0",
    fontSize: 11,
    fontFamily: "monospace",
    borderBottom: active ? "2px solid #f0c060" : "2px solid transparent",
  });

  const inputBase: React.CSSProperties = {
    flex: 1,
    padding: "6px 8px",
    fontSize: 12,
    fontFamily: "monospace",
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 4,
    color: "#cfe0ff",
    outline: "none",
  };

  const btnBase: React.CSSProperties = {
    padding: "6px 14px",
    fontSize: 12,
    fontFamily: "monospace",
    border: "1px solid rgba(240,192,96,0.4)",
    background: "rgba(240,192,96,0.15)",
    color: "#f0c060",
    borderRadius: 4,
    cursor: "pointer",
  };

  return (
    <div style={panelStyle}>
      {/* Header with 3 tabs */}
      <div style={{ display: "flex", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
        <button style={tabButtonStyle(tab === "chat")} onClick={() => setTab("chat")}>
          {"\u{1F4AC} \u8bbf\u5ba2\u804a\u5929"}
        </button>
        <button style={tabButtonStyle(tab === "bot")} onClick={() => setTab("bot")}>
          {"\u{1F916} AI\u52a9\u624b"}
        </button>
        <button style={{ ...tabButtonStyle(tab === "visitors"), display: "none" }} onClick={() => setTab("visitors")}>
          {"\u{1F465}"} ({onlineVisitors.length})
        </button>
        <button
          onClick={() => setExpanded(false)}
          style={{
            padding: "0 10px",
            cursor: "pointer",
            border: "none",
            background: "transparent",
            color: "#7a8aa0",
            fontSize: 16,
            fontFamily: "monospace",
          }}
          title={"\u6536\u8d77"}
        >
          {"\u00d7"}
        </button>
      </div>

      {/* === Tab 1: Visitor chat === */}
      {tab === "chat" && (
        <>
          <div
            ref={scrollRef}
            style={{ flex: 1, overflowY: "auto", padding: 8, maxHeight: "280px", minHeight: "120px" }}
          >
            {messages.length === 0 && (
              <div style={{ textAlign: "center", color: "#5a6a80", padding: "20px 0" }}>
                {"\u6682\u65e0\u6d88\u606f\uff0c\u53d1\u9001\u7b2c\u4e00\u6761\u6d88\u606f\u5f00\u59cb\u4ea4\u6d41\u5427\uff01"}
              </div>
            )}
            {messages.map((msg, i) => {
              const isSelf = msg.user_id === activeUserId;
              const key = messageIdentity(msg) ?? `${msg.user_id}:${msg.created_at ?? "legacy"}:${i}`;
              return (
                <div key={key} style={{ display: "flex", flexDirection: "column", alignItems: isSelf ? "flex-end" : "flex-start", marginBottom: 6 }}>
                  <span style={{ fontSize: 10, color: "#7a8aa0", marginBottom: 2 }}>
                    {isSelf ? "\u6211" : msg.display_name}{msg.created_at ? " \u00b7 " + new Date(msg.created_at).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"}) : ""}
                    {msg.delivery_status === "sending" ? " · 发送中" : ""}
                    {msg.delivery_status === "failed" ? " · 发送失败" : ""}
                  </span>
                  <span
                    style={{
                      display: "inline-block",
                      maxWidth: "85%",
                      padding: "4px 10px",
                      borderRadius: 8,
                      wordBreak: "break-word",
                      background: isSelf ? "rgba(240,192,96,0.15)" : "rgba(255,255,255,0.06)",
                      color: isSelf ? "#f0c060" : "#cfe0ff",
                    }}
                  >
                    {msg.message}
                  </span>
                </div>
              );
            })}
          </div>
          <div style={{ display: "flex", gap: 4, padding: 8, borderTop: "1px solid rgba(255,255,255,0.08)" }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`${activeDisplayName}...`}
              maxLength={500}
              style={inputBase}
            />
            <button
              onClick={handleSend}
              disabled={sending || !input.trim()}
              style={{ ...btnBase, opacity: sending || !input.trim() ? 0.5 : 1, cursor: sending || !input.trim() ? "not-allowed" : "pointer" }}
            >
              {sending ? "..." : "\u53d1\u9001"}
            </button>
          </div>
        </>
      )}

      {/* === Tab 2: AI Bot === */}
      {tab === "bot" && (
        <>
          <div
            ref={botScrollRef}
            style={{ flex: 1, overflowY: "auto", padding: 8, maxHeight: "280px", minHeight: "120px" }}
          >
            {botMessages.length === 0 && (
              <>
                <div style={{ textAlign: "center", color: "#7a8aa0", padding: "12px 0 8px" }}>
                  {"\u{1F916} \u6211\u662f Crossroads Agent Caf\u00e9 AI \u52a9\u624b\uff0c\u95ee\u6211\u4efb\u4f55\u95ee\u9898\uff01"}
                </div>
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", justifyContent: "center" }}>
                  {BOT_QUICK.map((q) => (
                    <button
                      key={q.label}
                      onClick={() => void sendBotPrompt(q.prompt)}
                      disabled={botBusy}
                      style={{
                        padding: "4px 10px",
                        fontSize: 11,
                        fontFamily: "monospace",
                        cursor: botBusy ? "not-allowed" : "pointer",
                        border: "1px solid rgba(240,192,96,0.25)",
                        background: "rgba(240,192,96,0.08)",
                        color: "#f0c060",
                        borderRadius: 10,
                        opacity: botBusy ? 0.5 : 1,
                      }}
                    >
                      {q.label}
                    </button>
                  ))}
                </div>
              </>
            )}
            {botMessages.map((m, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: m.role === "user" ? "flex-end" : "flex-start",
                  marginBottom: 6,
                }}
              >
                <span style={{ fontSize: 10, color: "#7a8aa0", marginBottom: 2 }}>
                  {m.role === "user" ? "\u6211" : "\u{1F916} AI"}
                </span>
                <span
                  style={{
                    display: "inline-block",
                    maxWidth: "90%",
                    padding: "4px 10px",
                    borderRadius: 8,
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                    lineHeight: 1.5,
                    background: m.role === "user" ? "rgba(240,192,96,0.15)" : "rgba(127,166,216,0.1)",
                    color: m.role === "user" ? "#f0c060" : "#cfe0ff",
                  }}
                >
                  {m.text}
                </span>
                {m.loginRequired && (
                  <button
                    type="button"
                    onClick={() => navigate(
                      m.checkoutId
                        ? `/login?checkout_id=${encodeURIComponent(m.checkoutId)}`
                        : "/login",
                    )}
                    style={{
                      marginTop: 5,
                      padding: "5px 10px",
                      fontSize: 11,
                      fontFamily: "monospace",
                      cursor: "pointer",
                      border: "1px solid rgba(96,165,250,0.4)",
                      background: "rgba(96,165,250,0.14)",
                      color: "#bfdbfe",
                      borderRadius: 4,
                    }}
                  >
                    登录后继续
                  </button>
                )}
                {/* Product cards */}
                {m.products && m.products.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 4, width: "100%" }}>
                    {m.products.map((p, j) => (
                      <div
                        key={j}
                        style={{
                          display: "flex",
                          gap: 6,
                          alignItems: "center",
                          padding: "4px 6px",
                          borderRadius: 4,
                          background: "rgba(240,192,96,0.06)",
                          border: "1px solid rgba(240,192,96,0.15)",
                        }}
                      >
                        {p.image && (
                          <img
                            src={`${(import.meta as unknown as { env: { DEV?: boolean } }).env?.DEV ? "http://localhost:8000" : ""}${p.image}`}
                            alt={p.name}
                            style={{ width: 32, height: 32, borderRadius: 4, objectFit: "cover", flexShrink: 0 }}
                            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                          />
                        )}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <span style={{ fontWeight: "bold", color: "#f0c060", fontSize: 11 }}>
                            {p.name} <span style={{ color: "#cfe0ff" }}>{"\u00a5"}{p.price.toFixed(2)}</span>
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {botBusy && <div style={{ opacity: 0.6, padding: "4px", color: "#7a8aa0" }}>{"AI \u6b63\u5728\u601d\u8003\u2026"}</div>}
          </div>
          <div style={{ display: "flex", gap: 4, padding: 8, borderTop: "1px solid rgba(255,255,255,0.08)" }}>
            <input
              value={botInput}
              onChange={(e) => setBotInput(e.target.value)}
              onKeyDown={handleBotKeyDown}
              placeholder={"\u95ee AI \u52a9\u624b\u4efb\u4f55\u95ee\u9898\u2026"}
              style={inputBase}
              disabled={botBusy}
            />
            <button
              onClick={handleBotSend}
              disabled={botBusy || !botInput.trim()}
              style={{ ...btnBase, opacity: botBusy || !botInput.trim() ? 0.5 : 1, cursor: botBusy || !botInput.trim() ? "not-allowed" : "pointer" }}
            >
              {botBusy ? "..." : "\u63d0\u95ee"}
            </button>
          </div>
        </>
      )}

      {/* === Tab 3: Visitors === */}
      {tab === "visitors" && (
        <div style={{ flex: 1, overflowY: "auto", padding: 8, maxHeight: "340px" }}>
          {onlineVisitors.length === 0 && (
            <div style={{ textAlign: "center", color: "#5a6a80", padding: "20px 0" }}>
              {"\u5f53\u524d\u6ca1\u6709\u5176\u4ed6\u5728\u7ebf\u8bbf\u5ba2"}
            </div>
          )}
          {onlineVisitors.map((v) => (
            <div
              key={v.agent_id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 8px",
                marginBottom: 4,
                borderRadius: 6,
                background: "rgba(255,255,255,0.04)",
              }}
            >
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 14,
                  fontWeight: "bold",
                  background: `hsl(${(v.agent_id * 37) % 360}, 60%, 45%)`,
                  color: "#fff",
                  flexShrink: 0,
                }}
              >
                {v.display_name.charAt(0)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, color: "#cfe0ff", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {v.display_name}
                  {v.user_id === activeUserId && <span style={{ color: "#f0c060", marginLeft: 4 }}>{"\uff08\u6211\uff09"}</span>}
                </div>
                <div style={{ fontSize: 10, color: "#5a6a80" }}>
                  {"\u5728\u7ebf \u00b7 "}{v.joined_at ? new Date(v.joined_at).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"}) : ""}
                </div>
              </div>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#4ade80", flexShrink: 0 }} />
            </div>
          ))}
          {/* Invite section */}
          <div style={{ marginTop: 12, padding: 8, textAlign: "center" }}>
            <button
              onClick={() => {
                const url = window.location.href;
                if (navigator.clipboard) {
                  navigator.clipboard.writeText(url).catch(() => {});
                }
              }}
              style={{
                width: "100%",
                padding: "8px",
                fontSize: 12,
                fontFamily: "monospace",
                cursor: "pointer",
                border: "1px solid rgba(74,222,128,0.3)",
                background: "rgba(74,222,128,0.1)",
                color: "#4ade80",
                borderRadius: 6,
              }}
            >
              {"\u{1F517} \u590d\u5236\u94fe\u63a5\u9080\u8bf7\u597d\u53cb"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
