// 浮动聊天面板：3D 场景内嵌的点单入口。匿名 user_id（localStorage 稳定）→ POST /chat。
// 顾客人偶由后端 customer_enter_scene 驱动进入 3D 场景；本组件只负责对话。
import { useCallback, useEffect, useRef, useState } from "react";
import { sendChat, getAnonUserId, type ChatProduct } from "../net/api";

type Msg = { role: "user" | "assistant"; text: string; products?: ChatProduct[] };

const PANEL: React.CSSProperties = {
  position: "absolute",
  bottom: 12,
  left: 12,
  width: "min(360px, calc(100vw - 24px))",
  maxHeight: 360,
  display: "flex",
  flexDirection: "column",
  background: "rgba(12,18,28,0.86)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 10,
  color: "#e8dfc0",
  fontFamily: "monospace",
  fontSize: 12,
  zIndex: 30,
  overflow: "hidden",
};
const HEADER: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  padding: "8px 10px",
  borderBottom: "1px solid rgba(255,255,255,0.08)",
  color: "#f0c060",
};
const LIST: React.CSSProperties = {
  flex: 1,
  overflowY: "auto",
  display: "flex",
  flexDirection: "column",
  gap: 4,
  padding: 8,
  maxHeight: 240,
};
const BUBBLE: React.CSSProperties = {
  padding: "6px 10px",
  borderRadius: 8,
  maxWidth: "85%",
  whiteSpace: "pre-wrap",
  lineHeight: 1.5,
  wordBreak: "break-word",
};
const INPUT_ROW: React.CSSProperties = { display: "flex", gap: 6, padding: 8, borderTop: "1px solid rgba(255,255,255,0.08)" };
const INPUT: React.CSSProperties = {
  flex: 1,
  background: "rgba(0,0,0,0.4)",
  border: "1px solid rgba(255,255,255,0.15)",
  borderRadius: 6,
  color: "#e8dfc0",
  padding: "6px 8px",
  fontFamily: "monospace",
  fontSize: 12,
  outline: "none",
};
const BTN: React.CSSProperties = {
  padding: "6px 12px",
  fontFamily: "monospace",
  fontSize: 12,
  cursor: "pointer",
  border: "1px solid rgba(240,192,96,0.5)",
  background: "rgba(240,192,96,0.18)",
  color: "#f0c060",
  borderRadius: 6,
};
const PRODUCT_CARD: React.CSSProperties = {
  display: "flex",
  gap: 8,
  alignItems: "center",
  padding: "6px 8px",
  marginTop: 6,
  borderRadius: 6,
  background: "rgba(240,192,96,0.08)",
  border: "1px solid rgba(240,192,96,0.2)",
};
const PRODUCT_IMG: React.CSSProperties = {
  width: 42,
  height: 42,
  borderRadius: 6,
  objectFit: "cover",
  flexShrink: 0,
};
const PRODUCT_INFO: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 2,
};
const PRODUCT_NAME: React.CSSProperties = {
  fontWeight: "bold",
  color: "#f0c060",
  fontSize: 12,
};
const PRODUCT_PRICE: React.CSSProperties = {
  color: "#e8dfc0",
  fontSize: 11,
};
const PRODUCT_DESC: React.CSSProperties = {
  color: "rgba(232,223,192,0.65)",
  fontSize: 10,
  lineHeight: 1.4,
};
const FAB: React.CSSProperties = {
  position: "absolute",
  bottom: 12,
  left: 12,
  zIndex: 30,
  padding: "8px 14px",
  fontFamily: "monospace",
  fontSize: 13,
  cursor: "pointer",
  border: "1px solid rgba(240,192,96,0.5)",
  background: "rgba(240,192,96,0.18)",
  color: "#f0c060",
  borderRadius: 8,
};

export function ChatPanel() {
  const [open, setOpen] = useState(true);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const [userId] = useState(() => getAnonUserId());
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      const res = await sendChat(userId, text);
      setMessages((m) => [...m, { role: "assistant", text: res.reply, products: res.products }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: `出错：${(e as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  }, [input, busy, userId]);

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={FAB}>💬 点单</button>
    );
  }

  return (
    <div style={PANEL}>
      <div style={HEADER}>
        <span>💬 AI 店长点单（匿名 #{userId}）</span>
        <button onClick={() => setOpen(false)} style={{ ...BTN, padding: "2px 8px" }}>—</button>
      </div>
      <div ref={scrollRef} style={LIST}>
        {messages.length === 0 && (
          <div style={{ opacity: 0.6, padding: "4px" }}>
            想喝什么？试试「来一杯美式」「推荐一下」「柑橘冷萃」…
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              ...BUBBLE,
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              background: m.role === "user" ? "rgba(240,192,96,0.18)" : "rgba(255,255,255,0.08)",
            }}
          >
            {m.text}
            {m.products && m.products.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 4 }}>
                {m.products.map((p, j) => (
                  <div key={j} style={PRODUCT_CARD}>
                    {p.image && (
                      <img
                        src={`${(import.meta as unknown as { env: { DEV?: boolean } }).env?.DEV ? "http://localhost:8000" : ""}${p.image}`}
                        alt={p.name}
                        style={PRODUCT_IMG}
                        onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                      />
                    )}
                    <div style={PRODUCT_INFO}>
                      <span style={PRODUCT_NAME}>{p.name} <span style={PRODUCT_PRICE}>¥{p.price.toFixed(2)}</span></span>
                      {p.description && (
                        <span style={PRODUCT_DESC}>{p.description.length > 50 ? p.description.slice(0, 50) + "…" : p.description}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && <div style={{ opacity: 0.6, padding: "4px" }}>店长正在回复…</div>}
      </div>
      <div style={INPUT_ROW}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }}
          placeholder="输入消息，回车发送"
          style={INPUT}
          disabled={busy}
        />
        <button onClick={send} disabled={busy || !input.trim()} style={{ ...BTN, opacity: busy || !input.trim() ? 0.5 : 1 }}>
          发送
        </button>
      </div>
    </div>
  );
}
