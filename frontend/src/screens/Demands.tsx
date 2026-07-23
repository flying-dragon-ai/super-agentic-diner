// 需求榜单 + 认领任务页面。
// 所有登录用户可发布需求、认领需求、完成需求。
import { useEffect, useState, useCallback } from "react";
import { useAuth } from "../auth/AuthProvider";
import {
  listDemands,
  createDemand,
  claimDemand,
  completeDemand,
  type Demand,
} from "../net/api";

const STATUS_TABS = [
  { key: "", label: "全部" },
  { key: "open", label: "待认领" },
  { key: "claimed", label: "进行中" },
  { key: "done", label: "已完成" },
] as const;

const STATUS_META: Record<string, { label: string; color: string; bg: string }> = {
  open: { label: "待认领", color: "#fbbf24", bg: "rgba(251,191,36,0.1)" },
  claimed: { label: "进行中", color: "#22d3ee", bg: "rgba(34,211,238,0.1)" },
  done: { label: "已完成", color: "#34d399", bg: "rgba(52,211,153,0.1)" },
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: "10px 12px",
  borderRadius: 8,
  border: "1px solid rgba(120,160,220,0.25)",
  background: "#0c1118",
  color: "#e8dfc0",
  fontSize: 14,
};

const btnStyle: React.CSSProperties = {
  padding: "8px 16px",
  borderRadius: 8,
  border: "none",
  cursor: "pointer",
  fontSize: 13,
  fontWeight: 600,
};

export default function Demands() {
  const { account } = useAuth();
  const [demands, setDemands] = useState<Demand[]>([]);
  const [tab, setTab] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // 发布表单
  const [title, setTitle] = useState("");
  const [desc, setDesc] = useState("");
  const [category, setCategory] = useState("");
  const [reward, setReward] = useState(0);
  const [publishing, setPublishing] = useState(false);

  const load = useCallback((status: string) => {
    setLoading(true);
    listDemands(status || undefined)
      .then((r) => setDemands(r.demands ?? []))
      .catch(() => setDemands([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(tab);
  }, [tab, load]);

  const handlePublish = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setPublishing(true);
    setError("");
    try {
      await createDemand({
        title: title.trim(),
        description: desc.trim(),
        category: category.trim(),
        reward_credits: reward,
      });
      setTitle("");
      setDesc("");
      setCategory("");
      setReward(0);
      load(tab);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "发布失败");
    } finally {
      setPublishing(false);
    }
  };

  const handleClaim = async (id: number) => {
    setError("");
    try {
      await claimDemand(id);
      load(tab);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "认领失败");
    }
  };

  const handleComplete = async (id: number) => {
    setError("");
    try {
      await completeDemand(id);
      load(tab);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "完成失败");
    }
  };

  const myId = (account as { account_id?: number })?.account_id;

  return (
    <div
      style={{
        width: "100vw",
        minHeight: "100vh",
        background: "#080c12",
        color: "#dfe8f5",
        fontFamily: "system-ui, sans-serif",
        padding: 24,
        boxSizing: "border-box",
        overflow: "auto",
      }}
    >
      <h1 style={{ margin: "0 0 20px", fontSize: 22, letterSpacing: 1 }}>
        📋 需求榜单 · 认领任务
      </h1>

      {/* 发布需求表单 */}
      <div
        style={{
          background: "#111827",
          borderRadius: 10,
          border: "1px solid rgba(255,255,255,0.08)",
          padding: 20,
          marginBottom: 16,
        }}
      >
        <h3 style={{ margin: "0 0 12px", fontSize: 15, color: "#fbbf24" }}>
          ✨ 发布新需求
        </h3>
        <form onSubmit={handlePublish}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
            <input
              style={inputStyle}
              placeholder="需求标题（必填）"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={128}
              required
            />
            <input
              style={inputStyle}
              placeholder="分类（可选，如：开发/设计/咨询）"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              maxLength={32}
            />
          </div>
          <textarea
            style={{ ...inputStyle, minHeight: 60, marginBottom: 10, resize: "vertical" }}
            placeholder="详细描述（可选）"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            maxLength={2000}
          />
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            <label style={{ fontSize: 13, color: "#7fa6d8" }}>奖励 Credits：</label>
            <input
              type="number"
              style={{ ...inputStyle, width: 120 }}
              value={reward}
              onChange={(e) => setReward(Math.max(0, parseInt(e.target.value) || 0))}
              min={0}
            />
            <button
              type="submit"
              disabled={publishing || !title.trim()}
              style={{
                ...btnStyle,
                background: publishing || !title.trim() ? "#333" : "#2563eb",
                color: "#fff",
              }}
            >
              {publishing ? "发布中..." : "发布需求"}
            </button>
          </div>
        </form>
        {error && (
          <div style={{ marginTop: 8, color: "#ef4444", fontSize: 13 }}>⚠ {error}</div>
        )}
      </div>

      {/* 状态过滤 */}
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        {STATUS_TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              ...btnStyle,
              background: tab === t.key ? "#2563eb" : "rgba(255,255,255,0.05)",
              color: tab === t.key ? "#fff" : "#8b9bb4",
              border: `1px solid ${tab === t.key ? "#2563eb" : "rgba(255,255,255,0.08)"}`,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 需求列表 */}
      {loading ? (
        <div style={{ padding: 40, textAlign: "center", color: "#5a6a82" }}>加载中...</div>
      ) : demands.length === 0 ? (
        <div style={{ padding: 40, textAlign: "center", color: "#5a6a82" }}>暂无需求</div>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {demands.map((d) => {
            const meta = STATUS_META[d.status] ?? STATUS_META.open;
            const isCreator = d.creator_id === myId;
            const isClaimer = d.claimer_id === myId;
            const canClaim = d.status === "open" && !isCreator;
            const canComplete =
              d.status === "claimed" && (isCreator || isClaimer);
            return (
              <div
                key={d.demand_id}
                style={{
                  background: "#111827",
                  borderRadius: 10,
                  border: `1px solid rgba(255,255,255,0.08)`,
                  borderLeft: `3px solid ${meta.color}`,
                  padding: 16,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    marginBottom: 8,
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 16, fontWeight: 600, color: "#e8dfc0", marginBottom: 4 }}>
                      {d.title}
                    </div>
                    <div style={{ display: "flex", gap: 12, fontSize: 12, color: "#5a6a82" }}>
                      <span>发布者：{d.creator_name ?? `#${d.creator_id}`}</span>
                      {d.claimer_name && <span>认领者：{d.claimer_name}</span>}
                      {d.category && <span>分类：{d.category}</span>}
                      {d.reward_credits > 0 && (
                        <span style={{ color: "#fbbf24" }}>🏆 {d.reward_credits} Credits</span>
                      )}
                    </div>
                  </div>
                  <span
                    style={{
                      padding: "3px 10px",
                      borderRadius: 12,
                      fontSize: 12,
                      fontWeight: 600,
                      color: meta.color,
                      background: meta.bg,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {meta.label}
                  </span>
                </div>
                {d.description && (
                  <div style={{ color: "#8b9bb4", fontSize: 13, lineHeight: 1.6, marginBottom: 8 }}>
                    {d.description}
                  </div>
                )}
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  {canClaim && (
                    <button
                      onClick={() => handleClaim(d.demand_id)}
                      style={{ ...btnStyle, background: "#0891b2", color: "#fff" }}
                    >
                      🤝 认领
                    </button>
                  )}
                  {canComplete && (
                    <button
                      onClick={() => handleComplete(d.demand_id)}
                      style={{ ...btnStyle, background: "#059669", color: "#fff" }}
                    >
                      ✅ 完成任务
                    </button>
                  )}
                  <span style={{ fontSize: 11, color: "#5a6a82" }}>
                    {d.created_at
                      ? `发布于 ${new Date(d.created_at).toLocaleString("zh-CN")}`
                      : ""}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
