import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api, clearToken, getToken, setToken } from "../api/client";
import type { SupportedLanguage, User } from "../api/types";
import i18n from "../i18n";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string, inviteCode: string) => Promise<void>;
  logout: () => Promise<void>;
  setLanguagePreference: (language: SupportedLanguage | null) => Promise<void>;
  // Re-fetches /auth/me so this tab picks up settings changed elsewhere (e.g. an admin
  // saving a new workspace main_language on the Company tab) without a full page reload.
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Once we know who's logged in, the account/workspace settings become authoritative
  // over whatever the browser-detected language guessed pre-login (see i18n/index.ts).
  // Callers that need the UI to have already switched language by the time they resume
  // (e.g. showing a toast right after) should await this alongside setUser rather than
  // relying on a reactive effect, which only runs on a later render.
  const syncLanguage = useCallback(async (loadedUser: User) => {
    await i18n.changeLanguage(loadedUser.preferred_language ?? loadedUser.workspace_main_language);
  }, []);

  const loadCurrentUser = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const currentUser = await api.get<User>("/auth/me");
      setUser(currentUser);
      await syncLanguage(currentUser);
    } catch {
      clearToken();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, [syncLanguage]);

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

  const setLanguagePreference = useCallback(
    async (language: SupportedLanguage | null) => {
      const updated = await api.patch<User>("/auth/me/language", { preferred_language: language });
      setUser(updated);
      await syncLanguage(updated);
    },
    [syncLanguage]
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
    () => ({
      user,
      isLoading,
      login,
      signup,
      logout,
      setLanguagePreference,
      refreshUser: loadCurrentUser,
    }),
    [user, isLoading, login, signup, logout, setLanguagePreference, loadCurrentUser]
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
