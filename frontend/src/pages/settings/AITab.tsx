import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api } from "../../api/client";
import type { WorkspaceSettings } from "../../api/types";
import Skeleton from "../../components/Skeleton";
import { useToast } from "../../context/ToastContext";
import { useSettingsContext } from "./SettingsLayout";
import { buildSettingsPayload } from "./settingsPayload";

const MODEL_SUGGESTIONS = ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"];
const EMBED_MODEL_SUGGESTIONS = ["mistral-embed"];

function apiKeyStatusText(settings: WorkspaceSettings, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (!settings.mistral_api_key_configured) {
    return t("sources.noApiKeyConfigured", { envVar: "MISTRAL_API_KEY" });
  }
  const suffix = settings.mistral_api_key_last4
    ? t("sources.endingIn", { last4: settings.mistral_api_key_last4 })
    : "";
  return settings.mistral_api_key_source === "workspace"
    ? t("sources.usingInAppKey", { suffix })
    : t("sources.usingEnvKey", { suffix });
}

export default function AITab() {
  const { t } = useTranslation("settings");
  const { showToast } = useToast();
  const { settings, setSettings, loadError } = useSettingsContext();
  const [isSaving, setIsSaving] = useState(false);
  const [isClearingKey, setIsClearingKey] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setIsSaving(true);
    try {
      const payload = buildSettingsPayload(settings);
      if (apiKeyInput.trim() !== "") {
        payload.mistral_api_key = apiKeyInput.trim();
      }
      const updated = await api.put<WorkspaceSettings>("/settings", payload);
      setSettings(updated);
      setApiKeyInput("");
      showToast(t("saved"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("saveFailed"), "error");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleClearApiKeyOverride() {
    if (!settings) return;
    setIsClearingKey(true);
    try {
      const updated = await api.put<WorkspaceSettings>("/settings", {
        ...buildSettingsPayload(settings),
        mistral_api_key: "",
      });
      setSettings(updated);
      setApiKeyInput("");
      showToast(t("ai.clearKeyToast"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("ai.clearKeyFailed"), "error");
    } finally {
      setIsClearingKey(false);
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
        <h2>{t("ai.title")}</h2>
        <p className="subtitle">{t("ai.subtitle")}</p>

        <div className="field-row">
          <label>
            {t("ai.summarizationModel")}
            <input
              list="mistral-model-suggestions"
              value={settings.mistral_model}
              onChange={(e) => setSettings({ ...settings, mistral_model: e.target.value })}
              required
            />
            <datalist id="mistral-model-suggestions">
              {MODEL_SUGGESTIONS.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </label>
          <label>
            {t("ai.triageModel")}
            <input
              list="mistral-model-suggestions"
              value={settings.mistral_triage_model}
              onChange={(e) => setSettings({ ...settings, mistral_triage_model: e.target.value })}
              required
            />
          </label>
        </div>

        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={settings.mistral_triage_enabled}
            onChange={(e) => setSettings({ ...settings, mistral_triage_enabled: e.target.checked })}
          />
          {t("ai.preFilterLabel")}
        </label>

        <div className="field-row">
          <label>
            {t("ai.embeddingModel")}
            <input
              list="mistral-embed-model-suggestions"
              value={settings.mistral_embed_model}
              onChange={(e) => setSettings({ ...settings, mistral_embed_model: e.target.value })}
              required
            />
            <datalist id="mistral-embed-model-suggestions">
              {EMBED_MODEL_SUGGESTIONS.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </label>
          <label>
            {t("ai.dedupeThreshold")}
            <input
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={settings.mistral_dedupe_similarity_threshold}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  mistral_dedupe_similarity_threshold: Number(e.target.value),
                })
              }
            />
          </label>
        </div>
        <p className="subtitle">{t("ai.dedupeHint")}</p>

        <label>
          {t("ai.apiKey")}
          <input
            type="password"
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
            placeholder={t("ai.apiKeyPlaceholder")}
            autoComplete="off"
          />
        </label>
        <p className="subtitle">{apiKeyStatusText(settings, t)}</p>
        {settings.mistral_api_key_source === "workspace" && (
          <button
            type="button"
            className="secondary"
            onClick={handleClearApiKeyOverride}
            disabled={isClearingKey}
          >
            {isClearingKey ? t("clearing") : t("clearOverride")}
          </button>
        )}
      </div>

      <button type="submit" disabled={isSaving}>
        {isSaving ? t("saving") : t("save")}
      </button>
    </form>
  );
}
