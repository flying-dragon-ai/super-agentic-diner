// Auth context: holds the logged-in account. /auth/me is checked on mount via
// the signed httpOnly cookie set by the backend on login/register.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getJson, postJson, putJson } from "../net/api";

export type Account = {
  user_id: number;
  username: string;
  nickname: string | null;
  gender?: string | null;
  specialty?: string | null;
  profession?: string | null;
  role?: "user" | "admin";
};

type AuthState = {
  account: Account | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (
    username: string,
    password: string,
    nickname?: string,
    extra?: { gender?: string; specialty?: string; profession?: string },
  ) => Promise<void>;
  updateProfile: (patch: {
    nickname?: string;
    gender?: string;
    specialty?: string;
    profession?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
};

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getJson<Account>("/auth/me")
      .then(setAccount)
      .catch(() => setAccount(null))
      .finally(() => setLoading(false));
  }, []);

  const login = async (username: string, password: string) => {
    setAccount(await postJson<Account>("/auth/login", { username, password }));
  };
  const register = async (
    username: string,
    password: string,
    nickname?: string,
    extra?: { gender?: string; specialty?: string; profession?: string },
  ) => {
    setAccount(
      await postJson<Account>("/auth/register", {
        username,
        password,
        nickname,
        ...extra,
      }),
    );
  };
  const updateProfile = async (patch: {
    nickname?: string;
    gender?: string;
    specialty?: string;
    profession?: string;
  }) => {
    const updated = await putJson<Account>("/auth/profile", patch);
    setAccount(updated);
  };
  const logout = async () => {
    await postJson<{ ok: boolean }>("/auth/logout", {});
    setAccount(null);
  };

  return <Ctx.Provider value={{ account, loading, login, register, updateProfile, logout }}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
