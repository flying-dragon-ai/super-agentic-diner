// Today hot topics panel for 3D scene top-left.
import { useEffect, useRef, useState } from "react";
import { getTodayTopics, type TodayTopic } from "../net/api";

const HEAT_COLORS = ["#ef4444", "#f97316", "#fbbf24", "#84cc16", "#22d3ee", "#a78bfa"];

export function TodayTopicsPanel({
  top = 12,
  wsStatus = "connecting",
  agentCount = 0,
}: {
  top?: number;
  wsStatus?: string;
  agentCount?: number;
}) {
  const [topics, setTopics] = useState<TodayTopic[]>([]);
  const [stats, setStats] = useState({ orders: 0, chats: 0 });
  const [loading, setLoading] = useState(true);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchTopics = async () => {
      try {
        const data = await getTodayTopics();
        if (!cancelled) {
          setTopics(data.topics ?? []);
          setStats({ orders: data.total_orders_today ?? 0, chats: data.total_chats_today ?? 0 });
          setLoading(false);
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    };
    void fetchTopics();
    pollRef.current = setInterval(fetchTopics, 15000);
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const panelStyle: React.CSSProperties = {
    position: "absolute",
    top,
    left: 12,
    zIndex: 20,
    width: "min(240px, calc(100vw - 24px))",
    background: "rgba(12,18,28,0.82)",
    backdropFilter: "blur(6px)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 8,
    padding: "8px 10px",
    fontFamily: "monospace",
    color: "#e8dfc0",
    overflow: "hidden",
  };

  if (loading) {
    return (
      <div style={panelStyle}>
        <div style={{ fontSize: 12, fontWeight: "bold", color: "#f0c060", marginBottom: 6 }}>
          {"\u{1F525} \u4eca\u65e5\u70ed\u5ea6"}
        </div>
        <div style={{ fontSize: 11, color: "#5a6a80", padding: "8px 0" }}>
          {"\u52a0\u8f7d\u4e2d\u2026"}
        </div>
      </div>
    );
  }

  return (
    <div style={panelStyle}>
      <div style={{ fontSize: 12, fontWeight: "bold", color: "#f0c060", display: "flex", alignItems: "center", gap: 4, marginBottom: 4 }}>
        {"\u{1F525} \u4eca\u65e5\u70ed\u5ea6"}
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 10, color: "rgba(232,223,192,0.4)" }}>{"\u00b7 15s"}</span>
      </div>
      <div style={{ fontSize: 10, color: "rgba(232,223,192,0.5)", marginBottom: 6 }}>
        {"\u{1F4E6}"} {stats.orders} {"\u5355 \u00b7 \u{1F4AC}"} {stats.chats} {"\u6761 \u00b7 WS:"} {wsStatus} {"\u00b7 \u{1F464}"} {agentCount}
      </div>
      {topics.length === 0 ? (
        <div style={{ fontSize: 11, color: "#5a6a80", padding: "6px 0", textAlign: "center" }}>
          {"\u8fd8\u6ca1\u6709\u70ed\u95e8\u8bdd\u9898\uff0c\u5feb\u6765\u70b9\u5355\u5427\uff01"}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
          {topics.map((t) => {
            const color = HEAT_COLORS[Math.min(t.rank - 1, HEAT_COLORS.length - 1)];
            const isDrink = t.type === "drink";
            return (
              <div key={t.label + t.type} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: "bold",
                    width: 16,
                    height: 16,
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                    background: t.rank <= 3 ? color : "rgba(255,255,255,0.1)",
                    color: t.rank <= 3 ? "#fff" : "#7a8aa0",
                  }}
                >
                  {t.rank}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 11,
                      color: "#e8dfc0",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      display: "flex",
                      alignItems: "center",
                      gap: 3,
                    }}
                  >
                    {isDrink ? "\u2615" : "\u{1F4AC}"} {t.label}
                    <span style={{ fontSize: 9, color: "#5a6a80" }}>
                      {isDrink ? "x" + t.count : t.count + "\u63d0"}
                    </span>
                  </div>
                  <div
                    style={{
                      marginTop: 2,
                      height: 4,
                      borderRadius: 2,
                      background:
                        "linear-gradient(90deg, " +
                        color +
                        " " +
                        t.heat +
                        "%, rgba(255,255,255,0.06) " +
                        t.heat +
                        "%)",
                      transition: "background 0.6s ease",
                    }}
                  />
                </div>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: "bold",
                    color,
                    width: 24,
                    textAlign: "right",
                    flexShrink: 0,
                  }}
                >
                  {t.heat}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
