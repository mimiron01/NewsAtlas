import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api } from "../../api/client";
import type { WorkspaceSettings } from "../../api/types";
import Skeleton from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import { useToast } from "../../context/ToastContext";
import { useSettingsContext } from "./SettingsLayout";
import { buildSettingsPayload } from "./settingsPayload";

export default function CompanyTab() {
  const { t } = useTranslation("settings");
  const { showToast } = useToast();
  const { refreshUser } = useAuth();
  const { settings, setSettings, loadError } = useSettingsContext();
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setIsSaving(true);
    try {
      const updated = await api.put<WorkspaceSettings>("/settings", buildSettingsPayload(settings));
      setSettings(updated);
      // main_language may have just changed; re-fetch /auth/me so the saving admin's own
      // UI (which follows preferred_language ?? workspace_main_language) updates instantly
      // instead of only after their next reload/login.
      await refreshUser();
      showToast(t("saved"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("saveFailed"), "error");
    } finally {
      setIsSaving(false);
    }
  }

  if (loadError) {
    return <p className="error-text">{loadError}</p>;
  }

  if (!settings) {
    return (
      <div className="panel-card">
        <Skeleton rows={4} />
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="panel-card">
        <h2>{t("company.title")}</h2>
        <p className="subtitle">{t("company.subtitle")}</p>

        <label>
          {t("company.companyName")}
          <input
            value={settings.company_name}
            onChange={(e) => setSettings({ ...settings, company_name: e.target.value })}
            required
          />
        </label>

        <label>
          {t("company.offeringDescription")}
          <textarea
            rows={8}
            value={settings.offering_description}
            onChange={(e) => setSettings({ ...settings, offering_description: e.target.value })}
            placeholder={t("company.offeringPlaceholder")}
          />
        </label>

        <label>
          {t("company.mainLanguage")}
          <select
            value={settings.main_language}
            onChange={(e) =>
              setSettings({ ...settings, main_language: e.target.value as "en" | "de" })
            }
          >
            <option value="en">English</option>
            <option value="de">Deutsch</option>
          </select>
          <span className="field-hint">{t("company.mainLanguageHint")}</span>
        </label>

        <div className="field-row">
          <label>
            {t("company.ingestionInterval")}
            <input
              type="number"
              min={1}
              max={48}
              value={settings.ingestion_interval_hours}
              onChange={(e) =>
                setSettings({ ...settings, ingestion_interval_hours: Number(e.target.value) })
              }
            />
          </label>
          <label>
            {t("company.digestSendTime")}
            <input
              type="time"
              value={settings.digest_send_time}
              onChange={(e) => setSettings({ ...settings, digest_send_time: e.target.value })}
            />
          </label>
        </div>
      </div>

      <button type="submit" disabled={isSaving}>
        {isSaving ? t("saving") : t("save")}
      </button>
    </form>
  );
}
