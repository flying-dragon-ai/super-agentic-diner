import { BrowserRouter, Routes, Route, Navigate, Link, useNavigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth/AuthProvider";
import { LoginPage, RegisterPage } from "./auth/AuthPages";
import OfficeScene from "./screens/OfficeScene";
import Dashboard from "./screens/Dashboard";
import MachineShowcase from "./screens/MachineShowcase";

function TopBar() {
  const { account, logout, loading } = useAuth();
  const nav = useNavigate();
  const sceneRoute =
    typeof window !== "undefined" && window.location.pathname.includes("/scene");
  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        zIndex: sceneRoute ? 5 : 50,
        display: "flex",
        gap: 8,
        alignItems: "center",
        padding: "8px 12px",
        pointerEvents: sceneRoute ? "none" : "auto",
        opacity: sceneRoute ? 0.45 : 1,
      }}
    >
      <Link to="/scene" style={navLink}>3D 咖啡厅</Link>
      <Link to="/dashboard" style={navLink}>大屏</Link>
      {loading ? null : account ? (
        <>
          <span style={{ color: "#9fb6d8", fontSize: 12, marginRight: 4 }}>{account.nickname || account.username}</span>
          <button onClick={async () => { await logout(); nav("/login"); }} style={btnSm}>登出</button>
        </>
      ) : (
        <button onClick={() => nav("/login")} style={btnSm}>登录</button>
      )}
    </div>
  );
}

const navLink: React.CSSProperties = { color: "#8ab4ff", fontSize: 12, textDecoration: "none", background: "rgba(0,0,0,0.4)", padding: "4px 10px", borderRadius: 6 };
const btnSm: React.CSSProperties = { background: "rgba(42,107,168,0.7)", color: "#fff", border: "none", borderRadius: 6, padding: "5px 12px", cursor: "pointer", fontSize: 12 };

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
