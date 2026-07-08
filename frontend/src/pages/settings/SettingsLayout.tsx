import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useOutletContext } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../../api/client";
import type { NewsUsageSummary, WorkspaceSettings } from "../../api/types";
import { usePageTitle } from "../../hooks/usePageTitle";

export interface SettingsContextValue {
  settings: WorkspaceSettings | null;
  setSettings: (settings: WorkspaceSettings) => void;
  loadError: string | null;
  newsUsage: NewsUsageSummary | null;
  reloadNewsUsage: () => void;
}

export function useSettingsContext(): SettingsContextValue {
  return useOutletContext<SettingsContextValue>();
}

export default function SettingsLayout() {
  const { t } = useTranslation("settings");
  usePageTitle(t("heading"));
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [newsUsage, setNewsUsage] = useState<NewsUsageSummary | null>(null);

  const TABS = [
    { to: "/settings/company", label: t("tabs.company") },
    { to: "/settings/sources", label: t("tabs.sources") },
    { to: "/settings/ai", label: t("tabs.ai") },
    { to: "/settings/usage", label: t("tabs.usage") },
    { to: "/settings/users", label: t("tabs.users") },
    { to: "/settings/logs", label: t("tabs.logs") },
  ];

  const reloadNewsUsage = useCallback(() => {
    api.get<NewsUsageSummary>("/news-usage").then(setNewsUsage).catch(() => undefined);
  }, []);

  useEffect(() => {
    api
      .get<WorkspaceSettings>("/settings")
      .then(setSettings)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("loadFailed")));
    reloadNewsUsage();
  }, [reloadNewsUsage, t]);

  const context: SettingsContextValue = { settings, setSettings, loadError, newsUsage, reloadNewsUsage };

  return (
    <div>
      <h2 className="settings-heading">{t("heading")}</h2>
      <nav className="settings-tabs">
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to} className={({ isActive }) => `settings-tab ${isActive ? "active" : ""}`}>
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <Outlet context={context} />
    </div>
  );
}
