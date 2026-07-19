// Login + Register pages. On success the signed cookie is set and we navigate
// to the 3D scene, or back to the Skill authorization page for device login.
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./AuthProvider";

const wrap: React.CSSProperties = {
  width: "100vw", height: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
  background: "radial-gradient(circle at 50% 30%, #182234, #0b0f14)", fontFamily: "system-ui, sans-serif",
};
const card: React.CSSProperties = {
  width: 380, padding: 24, borderRadius: 12, background: "rgba(12,18,28,0.92)",
  border: "1px solid rgba(120,160,220,0.18)", color: "#e8dfc0",
};
const input: React.CSSProperties = {
  width: "100%", boxSizing: "border-box", marginBottom: 10, padding: "10px 12px", borderRadius: 8,
  border: "1px solid rgba(120,160,220,0.25)", background: "#0c1118", color: "#e8dfc0", fontSize: 14,
};
const select: React.CSSProperties = {
  ...input, appearance: "none", cursor: "pointer",
};
const label: React.CSSProperties = {
  fontSize: 12, color: "rgba(180,200,230,0.7)", marginBottom: 4, display: "block",
};
const btn: React.CSSProperties = {
  width: "100%", padding: "11px 0", borderRadius: 8, border: "none", cursor: "pointer",
  background: "#2a6ba8", color: "#fff", fontWeight: 600, fontSize: 15, marginTop: 6,
};
const sectionDivider: React.CSSProperties = {
  borderTop: "1px solid rgba(120,160,220,0.12)", marginTop: 12, paddingTop: 12, marginBottom: 6,
};
const sectionLabel: React.CSSProperties = {
  fontSize: 12, color: "rgba(180,200,230,0.5)", marginBottom: 8,
};

function skillAuthorizationNext(search: string): string | null {
  const candidate = new URLSearchParams(search).get("next") || "";
  return candidate.startsWith("/skill/authorize?") ? candidate : null;
}

function finishAuthentication(search: string, nav: ReturnType<typeof useNavigate>) {
  const next = skillAuthorizationNext(search);
  if (next) {
    window.location.replace(next);
    return;
  }
  nav("/scene", { replace: true });
}

export function LoginPage() {
  const { login } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const next = skillAuthorizationNext(location.search);
  const nextQuery = next ? `?next=${encodeURIComponent(next)}` : "";
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try { await login(username, password); finishAuthentication(location.search, nav); }
    catch (e2) { setErr(String((e2 as Error).message)); }
    finally { setBusy(false); }
  };

  return (
    <div style={wrap}>
      <form style={card} onSubmit={submit}>
        <h2 style={{ marginTop: 0 }}>登录 · Crossroads Agent Café</h2>
        <input style={input} placeholder="用户名" value={username} onChange={(e) => setU(e.target.value)} autoFocus />
        <input style={input} type="password" placeholder="密码" value={password} onChange={(e) => setP(e.target.value)} />
        {err ? <div style={{ color: "#f87171", fontSize: 13, marginBottom: 10 }}>{err}</div> : null}
        <button style={btn} disabled={busy || !username || !password}>{busy ? "登录中…" : "登录"}</button>
        <div style={{ marginTop: 14, fontSize: 13, opacity: 0.7 }}>
          没有账号？<a style={{ color: "#8ab4ff" }} onClick={() => nav(`/register${nextQuery}`)} href="#">注册</a>
        </div>
      </form>
    </div>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const next = skillAuthorizationNext(location.search);
  const nextQuery = next ? `?next=${encodeURIComponent(next)}` : "";
  const [username, setU] = useState("");
  const [nickname, setN] = useState("");
  const [password, setP] = useState("");
  const [gender, setG] = useState("");
  const [specialty, setS] = useState("");
  const [profession, setProf] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await register(
        username, password, nickname || undefined,
        {
          gender: gender || undefined,
          specialty: specialty || undefined,
          profession: profession || undefined,
        },
      );
      finishAuthentication(location.search, nav);
    } catch (e2) { setErr(String((e2 as Error).message)); }
    finally { setBusy(false); }
  };

  return (
    <div style={wrap}>
      <form style={card} onSubmit={submit}>
        <h2 style={{ marginTop: 0 }}>注册 · Crossroads Agent Café</h2>
        <input style={input} placeholder="用户名（3-32位字母数字）" value={username} onChange={(e) => setU(e.target.value)} autoFocus />
        <input style={input} placeholder="昵称（可选）" value={nickname} onChange={(e) => setN(e.target.value)} />
        <input style={input} type="password" minLength={8} maxLength={64} placeholder="密码（8-64位）" value={password} onChange={(e) => setP(e.target.value)} />

        <div style={sectionDivider}>
          <div style={sectionLabel}>个人资料（可选，进入场景后展示）</div>
        </div>

        <label style={label}>性别</label>
        <select style={select} value={gender} onChange={(e) => setG(e.target.value)}>
          <option value="">不透露</option>
          <option value="male">男</option>
          <option value="female">女</option>
          <option value="other">其他</option>
        </select>

        <label style={label}>特长 / 签名技能</label>
        <input
          style={input}
          placeholder="如：战略咨询、全栈开发、数据分析"
          value={specialty}
          onChange={(e) => setS(e.target.value)}
        />

        <label style={label}>专业 / 职业领域</label>
        <input
          style={input}
          placeholder="如：资深架构师、产品经理、AI 研究员"
          value={profession}
          onChange={(e) => setProf(e.target.value)}
        />

        {err ? <div style={{ color: "#f87171", fontSize: 13, marginBottom: 10 }}>{err}</div> : null}
        <button style={btn} disabled={busy || !username || !password}>{busy ? "注册中…" : "注册并登录"}</button>
        <div style={{ marginTop: 14, fontSize: 13, opacity: 0.7 }}>
          已有账号？<a style={{ color: "#8ab4ff" }} onClick={() => nav(`/login${nextQuery}`)} href="#">去登录</a>
        </div>
      </form>
    </div>
  );
}
