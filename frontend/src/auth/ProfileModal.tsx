// Profile edit modal: lets logged-in users update nickname, gender, specialty,
// profession anytime. Calls PUT /auth/profile and refreshes the AuthProvider state.
import { useState } from "react";
import { useAuth, type Account } from "./AuthProvider";

const overlay: React.CSSProperties = {
  position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
  background: "rgba(0,0,0,0.65)", zIndex: 200,
  display: "flex", alignItems: "center", justifyContent: "center",
  fontFamily: "system-ui, sans-serif",
};
const modal: React.CSSProperties = {
  width: 400, padding: 28, borderRadius: 14,
  background: "rgba(12,18,28,0.96)",
  border: "1px solid rgba(120,160,220,0.22)",
  color: "#e8dfc0",
  boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
};
const input: React.CSSProperties = {
  width: "100%", boxSizing: "border-box", marginBottom: 10, padding: "10px 12px",
  borderRadius: 8, border: "1px solid rgba(120,160,220,0.25)",
  background: "#0c1118", color: "#e8dfc0", fontSize: 14,
};
const selectStyle: React.CSSProperties = { ...input, appearance: "none", cursor: "pointer" };
const labelStyle: React.CSSProperties = {
  fontSize: 12, color: "rgba(180,200,230,0.7)", marginBottom: 4, display: "block",
};
const btnRow: React.CSSProperties = {
  display: "flex", gap: 10, marginTop: 16,
};
const btnSave: React.CSSProperties = {
  flex: 1, padding: "11px 0", borderRadius: 8, border: "none", cursor: "pointer",
  background: "#2a6ba8", color: "#fff", fontWeight: 600, fontSize: 14,
};
const btnCancel: React.CSSProperties = {
  flex: 1, padding: "11px 0", borderRadius: 8, cursor: "pointer",
  background: "rgba(255,255,255,0.08)", color: "#ccc",
  border: "1px solid rgba(255,255,255,0.15)", fontSize: 14,
};

export function ProfileModal({ onClose }: { onClose: () => void }) {
  const { account, updateProfile } = useAuth();
  const [nickname, setN] = useState(account?.nickname || "");
  const [gender, setG] = useState(account?.gender || "");
  const [specialty, setS] = useState(account?.specialty || "");
  const [profession, setProf] = useState(account?.profession || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState(false);

  const save = async () => {
    setBusy(true);
    setErr("");
    setOk(false);
    try {
      await updateProfile({
        nickname: nickname || "",
        gender: gender || "",
        specialty: specialty || "",
        profession: profession || "",
      });
      setOk(true);
      setTimeout(() => onClose(), 800);
    } catch (e2) {
      setErr(String((e2 as Error).message));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={overlay} onClick={onClose}>
      <div style={modal} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ margin: "0 0 16px", color: "#8ab4ff" }}>编辑个人资料</h3>

        <label style={labelStyle}>昵称</label>
        <input
          style={input}
          placeholder="展示在场景中的名字"
          value={nickname}
          onChange={(e) => setN(e.target.value)}
        />

        <label style={labelStyle}>性别</label>
        <select style={selectStyle} value={gender} onChange={(e) => setG(e.target.value)}>
          <option value="">不透露</option>
          <option value="male">男</option>
          <option value="female">女</option>
          <option value="other">其他</option>
        </select>

        <label style={labelStyle}>特长 / 签名技能</label>
        <input
          style={input}
          placeholder="如：战略咨询、全栈开发、数据分析"
          value={specialty}
          onChange={(e) => setS(e.target.value)}
        />

        <label style={labelStyle}>专业 / 职业领域</label>
        <input
          style={input}
          placeholder="如：资深架构师、产品经理、AI 研究员"
          value={profession}
          onChange={(e) => setProf(e.target.value)}
        />

        {err ? <div style={{ color: "#f87171", fontSize: 13, marginBottom: 8 }}>{err}</div> : null}
        {ok ? <div style={{ color: "#34d399", fontSize: 13, marginBottom: 8 }}>✓ 已保存，刷新场景后生效</div> : null}

        <div style={btnRow}>
          <button style={btnCancel} onClick={onClose}>取消</button>
          <button style={btnSave} disabled={busy} onClick={save}>
            {busy ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}

// Small inline badge showing the user's specialty, used in the TopBar
export function SpecialtyBadge({ account }: { account: Account | null }) {
  if (!account?.specialty) return null;
  // Premium look for 首席 tags (gold gradient + glow)
  const isChief = account.specialty.startsWith("首席");
  return (
    <span
      style={{
        fontSize: 10, fontWeight: 600,
        color: isChief ? "#fff" : "#fbbf24",
        background: isChief
          ? "linear-gradient(135deg,rgba(251,191,36,0.35),rgba(245,158,11,0.25))"
          : "rgba(251,191,36,0.12)",
        padding: "2px 10px", borderRadius: 6, pointerEvents: "auto",
        whiteSpace: "nowrap",
        border: isChief ? "1px solid rgba(251,191,36,0.5)" : "1px solid rgba(251,191,36,0.2)",
        boxShadow: isChief ? "0 0 8px rgba(251,191,36,0.3)" : "none",
        textShadow: isChief ? "0 0 4px rgba(251,191,36,0.5)" : "none",
      }}
    >
      {isChief ? "\u2B50 " : ""}{account.specialty}
    </span>
  );
}
