// Login + Register pages. On success the signed cookie is set and we navigate
// to the 3D scene. Anonymous entry to the scene is still allowed (per plan the
// /chat contract stays backward compatible).
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./AuthProvider";

const wrap: React.CSSProperties = {
  width: "100vw", height: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
  background: "radial-gradient(circle at 50% 30%, #182234, #0b0f14)", fontFamily: "system-ui, sans-serif",
};
const card: React.CSSProperties = {
  width: 340, padding: 24, borderRadius: 12, background: "rgba(12,18,28,0.92)",
  border: "1px solid rgba(120,160,220,0.18)", color: "#e8dfc0",
};
const input: React.CSSProperties = {
  width: "100%", boxSizing: "border-box", marginBottom: 12, padding: "10px 12px", borderRadius: 8,
  border: "1px solid rgba(120,160,220,0.25)", background: "#0c1118", color: "#e8dfc0", fontSize: 14,
};
const btn: React.CSSProperties = {
  width: "100%", padding: "11px 0", borderRadius: 8, border: "none", cursor: "pointer",
  background: "#2a6ba8", color: "#fff", fontWeight: 600, fontSize: 15,
};

export function LoginPage() {
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try { await login(username, password); nav("/scene"); }
    catch (e2) { setErr(String((e2 as Error).message)); }
    finally { setBusy(false); }
  };

  return (
    <div style={wrap}>
      <form style={card} onSubmit={submit}>
        <h2 style={{ marginTop: 0 }}>登录 · Coffee AI Boss</h2>
        <input style={input} placeholder="用户名" value={username} onChange={(e) => setU(e.target.value)} autoFocus />
        <input style={input} type="password" placeholder="密码" value={password} onChange={(e) => setP(e.target.value)} />
        {err ? <div style={{ color: "#f87171", fontSize: 13, marginBottom: 10 }}>{err}</div> : null}
        <button style={btn} disabled={busy || !username || !password}>{busy ? "登录中…" : "登录"}</button>
        <div style={{ marginTop: 14, fontSize: 13, opacity: 0.7 }}>
          没有账号？<a style={{ color: "#8ab4ff" }} onClick={() => nav("/register")} href="#">注册</a>
          <span style={{ marginLeft: 10 }}><a style={{ color: "#8ab4ff" }} onClick={() => nav("/scene")} href="#">匿名进入 3D</a></span>
        </div>
      </form>
    </div>
  );
}

export function RegisterPage() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [username, setU] = useState("");
  const [nickname, setN] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try { await register(username, password, nickname || undefined); nav("/scene"); }
    catch (e2) { setErr(String((e2 as Error).message)); }
    finally { setBusy(false); }
  };

  return (
    <div style={wrap}>
      <form style={card} onSubmit={submit}>
        <h2 style={{ marginTop: 0 }}>注册 · Coffee AI Boss</h2>
        <input style={input} placeholder="用户名" value={username} onChange={(e) => setU(e.target.value)} autoFocus />
        <input style={input} placeholder="昵称（可选）" value={nickname} onChange={(e) => setN(e.target.value)} />
        <input style={input} type="password" placeholder="密码" value={password} onChange={(e) => setP(e.target.value)} />
        {err ? <div style={{ color: "#f87171", fontSize: 13, marginBottom: 10 }}>{err}</div> : null}
        <button style={btn} disabled={busy || !username || !password}>{busy ? "注册中…" : "注册并登录"}</button>
        <div style={{ marginTop: 14, fontSize: 13, opacity: 0.7 }}>
          已有账号？<a style={{ color: "#8ab4ff" }} onClick={() => nav("/login")} href="#">去登录</a>
        </div>
      </form>
    </div>
  );
}
