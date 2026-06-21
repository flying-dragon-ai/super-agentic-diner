import { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Navigate, Link, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import { LoginPage, RegisterPage } from "./auth/AuthPages";
import OfficeScene from "./screens/OfficeScene";
import Dashboard from "./screens/Dashboard";
import MachineShowcase from "./screens/MachineShowcase";
import { isMuted, subscribeMute, toggleMute } from "./sounds/sceneMusic";

function TopBar() {
  const { account, logout, loading } = useAuth();
  const nav = useNavigate();
  const [muted, setMuted] = useState(isMuted());
  useEffect(() => subscribeMute(setMuted), []);
  return (
    <div
      style={{
        position: "fixed",
        top: 12,
        right: 12,
        zIndex: 50,
        display: "flex",
        gap: 10,
        alignItems: "center",
        justifyContent: "flex-end",
        flexWrap: "wrap",
        maxWidth: "calc(100vw - 24px)",
        padding: "8px 12px",
        // Container is click-through so it never blocks the 3D canvas drag/select;
        // each interactive child re-enables pointer events. The translucent panel
        // + blur keeps labels legible over any scene background (previously 0.45
        // opacity text overlapped unreadably with the bar/lobby furniture, and the
        // whole bar was unclickable).
        pointerEvents: "none",
        background: "rgba(12,18,28,0.72)",
        border: "1px solid rgba(80,130,200,0.22)",
        borderRadius: 10,
        boxShadow: "0 4px 18px rgba(0,0,0,0.35)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
      }}
    >
      <Link to="/scene" style={navLink}>3D EvoMap 进化咖啡馆</Link>
      <Link to="/dashboard" style={navLink}>大屏</Link>
      <button
        onClick={() => toggleMute()}
        style={muteBtn}
        title={muted ? "打开背景音乐" : "静音背景音乐"}
      >
        {muted ? "🔇" : "🔊"}
      </button>
      {loading ? null : account ? (
        <>
          <span style={{ color: "#cdd9ee", fontSize: 12, marginRight: 2, pointerEvents: "auto", whiteSpace: "nowrap" }}>
            {account.nickname || account.username}
          </span>
          <button onClick={async () => { await logout(); nav("/login"); }} style={btnSm}>登出</button>
        </>
      ) : (
        <button onClick={() => nav("/login")} style={btnSm}>登录</button>
      )}
    </div>
  );
}

const navLink: React.CSSProperties = { color: "#8ab4ff", fontSize: 12, textDecoration: "none", background: "rgba(0,0,0,0.4)", padding: "4px 10px", borderRadius: 6, pointerEvents: "auto" };
const btnSm: React.CSSProperties = { background: "rgba(42,107,168,0.7)", color: "#fff", border: "none", borderRadius: 6, padding: "5px 12px", cursor: "pointer", fontSize: 12, pointerEvents: "auto" };
const muteBtn: React.CSSProperties = { background: "rgba(0,0,0,0.4)", color: "#fff", border: "none", borderRadius: 6, padding: "4px 8px", cursor: "pointer", fontSize: 14, lineHeight: 1, pointerEvents: "auto" };

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter basename="/3d">
        <TopBar />
        <Routes>
          <Route path="/" element={<Navigate to="/scene" replace />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/scene" element={<OfficeScene />} />
          <Route path="/machines" element={<MachineShowcase />} />
          <Route path="/dashboard" element={<Dashboard />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
