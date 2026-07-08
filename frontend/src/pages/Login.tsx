import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";
import EmptyStateIllustration from "../components/icons/EmptyStateIllustration";
import { usePageTitle } from "../hooks/usePageTitle";

export default function Login() {
  usePageTitle();
  const { t } = useTranslation("auth");
  const { login, signup } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await signup(email, password, name, inviteCode);
      }
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("genericError"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={handleSubmit}>
        <div className="auth-illustration">
          <EmptyStateIllustration />
        </div>
        <h1>{t("brand")}</h1>
        <p className="subtitle">
          {mode === "login" ? t("subtitleLogin") : t("subtitleSignup")}
        </p>

        {mode === "signup" && (
          <label>
            {t("name")}
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
        )}
        <label>
          {t("email")}
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          {t("password")}
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={10}
          />
          <span className="field-hint">{t("passwordHint")}</span>
        </label>
        {mode === "signup" && (
          <label>
            {t("inviteCode")}
            <input
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              required
              autoComplete="off"
            />
          </label>
        )}

        {error && <p className="error-text">{error}</p>}

        <button type="submit" disabled={isSubmitting}>
          {mode === "login" ? t("signIn") : t("createAccount")}
        </button>

        <button
          type="button"
          className="link-button"
          onClick={() => setMode(mode === "login" ? "signup" : "login")}
        >
          {mode === "login" ? t("switchToSignup") : t("switchToLogin")}
        </button>
      </form>
    </div>
  );
}
