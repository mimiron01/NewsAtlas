import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, clearToken, getToken, setToken } from "../api/client";
import type { User } from "../api/types";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string, inviteCode: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadCurrentUser = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const currentUser = await api.get<User>("/auth/me");
      setUser(currentUser);
    } catch {
      clearToken();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCurrentUser();
  }, [loadCurrentUser]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await api.post<TokenResponse>("/auth/login", { email, password });
    setToken(response.access_token);
    await loadCurrentUser();
  }, [loadCurrentUser]);

  const signup = useCallback(
    async (email: string, password: string, name: string, inviteCode: string) => {
      const response = await api.post<TokenResponse>("/auth/signup", {
        email,
        password,
        name,
        invite_code: inviteCode,
      });
      setToken(response.access_token);
      await loadCurrentUser();
    },
    [loadCurrentUser]
  );

  const logout = useCallback(async () => {
    try {
      // Best-effort: revokes the token server-side (see /auth/logout). Still clear the
      // local copy below even if this fails (e.g. offline), so the UI doesn't get stuck.
      await api.post("/auth/logout");
    } catch {
      // ignore
    }
    clearToken();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, login, signup, logout }),
    [user, isLoading, login, signup, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
