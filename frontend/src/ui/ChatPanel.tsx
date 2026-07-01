// 浮动聊天面板：3D 场景内嵌的点单入口。匿名 user_id（localStorage 稳定）→ POST /chat。
// 顾客人偶由后端 customer_enter_scene 驱动进入 3D 场景；本组件只负责对话。
// 增强版：含饮品分类快捷按钮（全部/热饮/冷饮/特调）
import { useCallback, useEffect, useRef, useState } from "react";
import { sendChat, getAnonUserId, type ChatProduct } from "../net/api";

type Msg = { role: "user" | "assistant"; text: string; products?: ChatProduct[] };

const PANEL: React.CSSProperties = {
  position: "absolute",
  bottom: 12,
  left: 12,
  width: "min(360px, calc(100vw - 24px))",
  maxHeight: 360,
  display: "none",
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

const QUICK_CATS = [
  { label: "\u2615 \u5168\u90e8", prompt: "\u770b\u770b\u83dc\u5355" },
  { label: "\u2698\ufe0f \u70ed\u996e", prompt: "\u63a8\u8350\u4e00\u676f\u70ed\u996e" },
  { label: "\ud83e\uddca \u51b7\u996e", prompt: "\u63a8\u8350\u4e00\u676f\u51b7\u996e\u6216\u51b0\u5496\u5561" },
  { label: "\u2728 \u7279\u8c03", prompt: "\u6709\u4ec0\u4e48\u5b63\u8282\u6027\u7279\u8c03\u996e\u54c1\uff1f" },
];

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
      setMessages((m) => [...m, { role: "assistant", text: `\u51fa\u9519\uff1a${(e as Error).message}` }]);
    } finally {
      setBusy(false);
    }
  }, [input, busy, userId]);

  // Quick-send a preset category prompt directly (no manual typing needed).
  const quickSend = useCallback((text: string) => {
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);
    void (async () => {
      try {
        const res = await sendChat(userId, text);
        setMessages((m) => [...m, { role: "assistant", text: res.reply, products: res.products }]);
      } catch (e) {
        setMessages((m) => [...m, { role: "assistant", text: `\u51fa\u9519\uff1a${(e as Error).message}` }]);
      } finally {
        setBusy(false);
      }
    })();
  }, [userId]);

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} style={FAB}>{"\u{1F4AC} 点单"}</button>
    );
  }

  return (
    <div style={PANEL}>
      <div style={HEADER}>
        <span>{`\u{1F4AC} AI 店长点单（匿名 #${userId}）`}</span>
        <button onClick={() => setOpen(false)} style={{ ...BTN, padding: "2px 8px" }}>{"—"}</button>
      </div>
      <div ref={scrollRef} style={LIST}>
        {messages.length === 0 && (
          <div style={{ opacity: 0.6, padding: "4px" }}>
            {"\u60f3\u559d\u4ec0\u4e48\uff1f\u8bd5\u8bd5\u300c\u6765\u4e00\u676f\u7f8e\u5f0f\u300d\u300c\u63a8\u8350\u4e00\u4e0b\u300d\u300c\u67d1\u6a58\u51b7\u8403\u300d\u2026"}
          </div>
        )}
        {messages.length === 0 && (
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap", padding: "0 4px 6px" }}>
            {QUICK_CATS.map((cat) => (
              <button
                key={cat.label}
                onClick={() => quickSend(cat.prompt)}
                disabled={busy}
                style={{
                  padding: "4px 10px",
                  fontSize: 11,
                  fontFamily: "monospace",
                  cursor: busy ? "not-allowed" : "pointer",
                  border: "1px solid rgba(240,192,96,0.25)",
                  background: "rgba(240,192,96,0.08)",
                  color: "#f0c060",
                  borderRadius: 10,
                  opacity: busy ? 0.5 : 1,
                }}
              >
                {cat.label}
              </button>
            ))}
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
                      <span style={PRODUCT_NAME}>{p.name} <span style={PRODUCT_PRICE}>{"\u00a5"}{p.price.toFixed(2)}</span></span>
                      {p.description && (
                        <span style={PRODUCT_DESC}>{p.description.length > 50 ? p.description.slice(0, 50) + "\u2026" : p.description}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && <div style={{ opacity: 0.6, padding: "4px" }}>{"\u5e97\u957f\u6b63\u5728\u56de\u590d\u2026"}</div>}
      </div>
      <div style={INPUT_ROW}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }}
          placeholder={"\u8f93\u5165\u6d88\u606f\uff0c\u56de\u8f66\u53d1\u9001"}
          style={INPUT}
          disabled={busy}
        />
        <button onClick={send} disabled={busy || !input.trim()} style={{ ...BTN, opacity: busy || !input.trim() ? 0.5 : 1 }}>
          {"\u53d1\u9001"}
        </button>
      </div>
    </div>
  );
}
