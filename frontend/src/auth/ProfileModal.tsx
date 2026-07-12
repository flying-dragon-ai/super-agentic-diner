// Profile edit modal: lets logged-in users update nickname, gender, specialty,
// profession anytime. Calls PUT /auth/profile and refreshes the AuthProvider state.
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useAuth, type Account } from "./AuthProvider";

const overlay: React.CSSProperties = {
  position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
  background: "rgba(0,0,0,0.65)", zIndex: 200,
  display: "flex", alignItems: "center", justifyContent: "center",
  fontFamily: "system-ui, sans-serif",
  pointerEvents: "auto",
  padding: 16,
};
const modal: React.CSSProperties = {
  width: 400, maxWidth: "calc(100vw - 32px)", maxHeight: "calc(100vh - 32px)",
  overflowY: "auto", padding: 28, borderRadius: 14,
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
  const dialogRef = useRef<HTMLDivElement>(null);
  const firstInputRef = useRef<HTMLInputElement>(null);
  const busyRef = useRef(false);
  const closeTimerRef = useRef<number | null>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    busyRef.current = busy;
  }, [busy]);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const focusTimer = window.setTimeout(() => firstInputRef.current?.focus(), 0);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.clearTimeout(focusTimer);
      if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus();
    };
  }, []);

  const save = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
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
      closeTimerRef.current = window.setTimeout(() => onCloseRef.current(), 700);
    } catch (e2) {
      setErr(String((e2 as Error).message));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      style={overlay}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busyRef.current) onClose();
      }}
    >
      <div
        ref={dialogRef}
        style={modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="profile-dialog-title"
        aria-describedby="profile-dialog-description"
        aria-busy={busy}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <h3 id="profile-dialog-title" style={{ margin: "0 0 6px", color: "#8ab4ff" }}>编辑个人资料</h3>
          <p id="profile-dialog-description" style={{ margin: "0 0 16px", color: "rgba(180,200,230,0.65)", fontSize: 12 }}>
            保存后，顶部资料会立即更新；场景人物资料会在后端 presence 同步后刷新。
          </p>

        <label htmlFor="profile-nickname" style={labelStyle}>昵称</label>
        <input
          id="profile-nickname"
          ref={firstInputRef}
          style={input}
          placeholder="展示在场景中的名字"
          value={nickname}
          onChange={(e) => setN(e.target.value)}
          maxLength={64}
          autoComplete="nickname"
        />

        <label htmlFor="profile-gender" style={labelStyle}>性别</label>
        <select id="profile-gender" style={selectStyle} value={gender} onChange={(e) => setG(e.target.value)}>
          <option value="">不透露</option>
          <option value="male">男</option>
          <option value="female">女</option>
          <option value="other">其他</option>
        </select>

        <label htmlFor="profile-specialty" style={labelStyle}>特长 / 签名技能</label>
        <input
          id="profile-specialty"
          style={input}
          placeholder="如：战略咨询、全栈开发、数据分析"
          value={specialty}
          onChange={(e) => setS(e.target.value)}
          maxLength={128}
        />

        <label htmlFor="profile-profession" style={labelStyle}>专业 / 职业领域</label>
        <input
          id="profile-profession"
          style={input}
          placeholder="如：资深架构师、产品经理、AI 研究员"
          value={profession}
          onChange={(e) => setProf(e.target.value)}
          maxLength={128}
        />

        <div aria-live="polite">
          {err ? <div style={{ color: "#f87171", fontSize: 13, marginBottom: 8 }}>{err}</div> : null}
          {ok ? <div style={{ color: "#34d399", fontSize: 13, marginBottom: 8 }}>✓ 已保存并立即更新</div> : null}
        </div>

        <div style={btnRow}>
          <button type="button" style={{ ...btnCancel, opacity: busy ? 0.55 : 1 }} disabled={busy} onClick={onClose}>取消</button>
          <button type="submit" style={{ ...btnSave, opacity: busy ? 0.65 : 1, cursor: busy ? "wait" : "pointer" }} disabled={busy}>
            {busy ? "保存中…" : "保存"}
          </button>
        </div>
        </form>
      </div>
    </div>,
    document.body,
  );
}

// Small inline badge showing the user's specialty, used in the TopBar
export function SpecialtyBadge({ account }: { account: Account | null }) {
  if (!account?.specialty && !account?.profession) return null;
  // Premium look for 首席 tags (gold gradient + glow)
  const isChief = account.specialty?.startsWith("首席") ?? false;
  return (
    <>
      {account.specialty ? (
        <span
          title={`特长：${account.specialty}`}
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
      ) : null}
      {account.profession ? (
        <span
          title={`职业：${account.profession}`}
          style={{
            fontSize: 10,
            color: "#bfdbfe",
            background: "rgba(96,165,250,0.12)",
            padding: "2px 10px",
            borderRadius: 6,
            pointerEvents: "auto",
            whiteSpace: "nowrap",
            border: "1px solid rgba(96,165,250,0.24)",
          }}
        >
          {account.profession}
        </span>
      ) : null}
    </>
  );
}
