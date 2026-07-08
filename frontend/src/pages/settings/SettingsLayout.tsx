import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useOutletContext } from "react-router-dom";

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

const TABS = [
  { to: "/settings/company", label: "Company" },
  { to: "/settings/sources", label: "News sources" },
  { to: "/settings/ai", label: "AI configuration" },
  { to: "/settings/usage", label: "AI usage" },
  { to: "/settings/users", label: "Users" },
  { to: "/settings/logs", label: "Logs" },
];

export default function SettingsLayout() {
  usePageTitle("Settings");
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [newsUsage, setNewsUsage] = useState<NewsUsageSummary | null>(null);

  const reloadNewsUsage = useCallback(() => {
    api.get<NewsUsageSummary>("/news-usage").then(setNewsUsage).catch(() => undefined);
  }, []);

  useEffect(() => {
    api
      .get<WorkspaceSettings>("/settings")
      .then(setSettings)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Failed to load settings"));
    reloadNewsUsage();
  }, [reloadNewsUsage]);

  const context: SettingsContextValue = { settings, setSettings, loadError, newsUsage, reloadNewsUsage };

  return (
    <div>
      <h2 className="settings-heading">Settings</h2>
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
