// Visitor social panel: combines an online visitor list with a real-time chat
// panel. Messages arrive via the WebSocket event stream (visitor.chat events)
// and are also fetched from the REST history endpoint on mount.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getAnonUserId,
  getOnlineVisitors,
  getVisitorChatHistory,
  sendVisitorChat,
  type OnlineVisitor,
  type VisitorChatMessage,
} from "../net/api";

type Props = {
  // Visitor chat events forwarded from the WebSocket handler.
  onVisitorChatEvent?: ((handler: (msg: VisitorChatMessage) => void) => void) | null;
  // Called when the panel wants to register its chat-event consumer.
  registerChatConsumer?: (handler: (msg: VisitorChatMessage) => void) => void;
};

const ANON_NAME_KEY = "coffee_visitor_display_name";

function getDisplayName(): string {
  try {
    const stored = localStorage.getItem(ANON_NAME_KEY);
    if (stored) return stored;
  } catch {
    // localStorage not available
  }
  const names = ["咖啡爱好者", "拿铁星人", "美式先锋", "摩卡达人", "卡布奇诺之友", "浓缩信徒"];
  const name = names[Math.floor(Math.random() * names.length)];
  try {
    localStorage.setItem(ANON_NAME_KEY, name);
  } catch {
    // ignore
  }
  return name;
}

export function VisitorSocialPanel({ registerChatConsumer }: Props) {
  const [messages, setMessages] = useState<VisitorChatMessage[]>([]);
  const [onlineVisitors, setOnlineVisitors] = useState<OnlineVisitor[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [tab, setTab] = useState<"chat" | "visitors">("chat");
  const [displayName] = useState(getDisplayName);
  const userId = useRef(getAnonUserId());
  const scrollRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load chat history on mount.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getVisitorChatHistory(50);
        if (!cancelled && data.messages) {
          setMessages(data.messages);
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
    registerChatConsumer((msg: VisitorChatMessage) => {
      setMessages((prev) => [...prev.slice(-99), msg]);
    });
  }, [registerChatConsumer]);

  // Auto-scroll to bottom on new messages.
  useEffect(() => {
    if (scrollRef.current && expanded && tab === "chat") {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, expanded, tab]);

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || sending) return;
    setSending(true);
    const msg: VisitorChatMessage = {
      user_id: userId.current,
      display_name: displayName,
      message: trimmed,
    };
    // Optimistic append.
    setMessages((prev) => [...prev.slice(-99), msg]);
    setInput("");
    try {
      await sendVisitorChat(userId.current, displayName, trimmed);
    } catch {
      // If REST fails, the message was optimistic — keep it but show no error toast.
    } finally {
      setSending(false);
    }
  }, [input, sending, displayName]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    },
    [handleSend],
  );

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
        💬 访客交流 ({onlineVisitors.length} 在线)
      </button>
    );
  }

  const panelStyle: React.CSSProperties = {
    position: "absolute",
    bottom: 12,
    left: 12,
    zIndex: 30,
    width: "min(320px, calc(100vw - 24px))",
    maxHeight: "400px",
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
    fontSize: 12,
    fontFamily: "monospace",
    borderBottom: active ? "2px solid #f0c060" : "2px solid transparent",
  });

  return (
    <div style={panelStyle}>
      {/* Header with tabs */}
      <div style={{ display: "flex", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
        <button style={tabButtonStyle(tab === "chat")} onClick={() => setTab("chat")}>
          💬 访客聊天
        </button>
        <button style={tabButtonStyle(tab === "visitors")} onClick={() => setTab("visitors")}>
          👥 在线 ({onlineVisitors.length})
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
          title="收起"
        >
          ×
        </button>
      </div>

      {/* Chat tab */}
      {tab === "chat" && (
        <>
          <div
            ref={scrollRef}
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "8px",
              maxHeight: "260px",
              minHeight: "120px",
            }}
          >
            {messages.length === 0 && (
              <div style={{ textAlign: "center", color: "#5a6a80", padding: "20px 0" }}>
                暂无消息，发送第一条消息开始交流吧！
              </div>
            )}
            {messages.map((msg, i) => {
              const isSelf = msg.user_id === userId.current;
              return (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: isSelf ? "flex-end" : "flex-start",
                    marginBottom: 6,
                  }}
                >
                  <span
                    style={{
                      fontSize: 10,
                      color: "#7a8aa0",
                      marginBottom: 2,
                    }}
                  >
                    {isSelf ? "我" : msg.display_name}
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
          {/* Input */}
          <div style={{ display: "flex", gap: 4, padding: 8, borderTop: "1px solid rgba(255,255,255,0.08)" }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`以「${displayName}」身份发言...`}
              maxLength={500}
              style={{
                flex: 1,
                padding: "6px 8px",
                fontSize: 12,
                fontFamily: "monospace",
                background: "rgba(255,255,255,0.05)",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: 4,
                color: "#cfe0ff",
                outline: "none",
              }}
            />
            <button
              onClick={handleSend}
              disabled={sending || !input.trim()}
              style={{
                padding: "6px 14px",
                fontSize: 12,
                fontFamily: "monospace",
                cursor: sending || !input.trim() ? "not-allowed" : "pointer",
                border: "1px solid rgba(240,192,96,0.4)",
                background: sending ? "rgba(240,192,96,0.08)" : "rgba(240,192,96,0.15)",
                color: "#f0c060",
                borderRadius: 4,
                opacity: sending || !input.trim() ? 0.5 : 1,
              }}
            >
              {sending ? "..." : "发送"}
            </button>
          </div>
        </>
      )}

      {/* Visitors tab */}
      {tab === "visitors" && (
        <div style={{ flex: 1, overflowY: "auto", padding: 8, maxHeight: "320px" }}>
          {onlineVisitors.length === 0 && (
            <div style={{ textAlign: "center", color: "#5a6a80", padding: "20px 0" }}>
              当前没有其他在线访客
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
                  {v.user_id === userId.current && <span style={{ color: "#f0c060", marginLeft: 4 }}>（我）</span>}
                </div>
                <div style={{ fontSize: 10, color: "#5a6a80" }}>
                  在线 · {v.joined_at ? new Date(v.joined_at).toLocaleTimeString() : ""}
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
              🔗 复制链接邀请好友
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
