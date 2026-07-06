import { FormEvent, useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { WorkspaceSettings, WorkspaceSettingsUpdatePayload } from "../api/types";
import Skeleton from "../components/Skeleton";
import { useToast } from "../context/ToastContext";
import { usePageTitle } from "../hooks/usePageTitle";

const MODEL_SUGGESTIONS = ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"];
const EMBED_MODEL_SUGGESTIONS = ["mistral-embed"];

function apiKeyStatusText(settings: WorkspaceSettings): string {
  if (!settings.mistral_api_key_configured) {
    return "No API key configured — set one below or via the MISTRAL_API_KEY environment variable.";
  }
  const suffix = settings.mistral_api_key_last4 ? ` ending in ...${settings.mistral_api_key_last4}` : "";
  return settings.mistral_api_key_source === "workspace"
    ? `Using an in-app key${suffix}.`
    : `Using a key from the server's environment variable${suffix}.`;
}

export default function SettingsProfile() {
  usePageTitle("Company profile");
  const { showToast } = useToast();
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isClearingKey, setIsClearingKey] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState("");

  useEffect(() => {
    api
      .get<WorkspaceSettings>("/settings")
      .then(setSettings)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Failed to load settings"));
  }, []);

  function basePayload(settings: WorkspaceSettings): WorkspaceSettingsUpdatePayload {
    return {
      company_name: settings.company_name,
      offering_description: settings.offering_description,
      digest_send_time: settings.digest_send_time,
      ingestion_interval_hours: settings.ingestion_interval_hours,
      mistral_model: settings.mistral_model,
      mistral_triage_model: settings.mistral_triage_model,
      mistral_embed_model: settings.mistral_embed_model,
      mistral_triage_enabled: settings.mistral_triage_enabled,
      mistral_dedupe_similarity_threshold: settings.mistral_dedupe_similarity_threshold,
    };
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setIsSaving(true);
    try {
      const payload = basePayload(settings);
      if (apiKeyInput.trim() !== "") {
        payload.mistral_api_key = apiKeyInput.trim();
      }
      const updated = await api.put<WorkspaceSettings>("/settings", payload);
      setSettings(updated);
      setApiKeyInput("");
      showToast("Settings saved.", "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to save settings", "error");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleClearApiKeyOverride() {
    if (!settings) return;
    setIsClearingKey(true);
    try {
      const updated = await api.put<WorkspaceSettings>("/settings", {
        ...basePayload(settings),
        mistral_api_key: "",
      });
      setSettings(updated);
      setApiKeyInput("");
      showToast("In-app API key override cleared.", "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to clear API key", "error");
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
        <h2>Company profile</h2>
        <p className="subtitle">
          This description is given to the AI model so it can explain why each news signal matters
          for your business and draft relevant outreach snippets.
        </p>

        <label>
          Company name
          <input
            value={settings.company_name}
            onChange={(e) => setSettings({ ...settings, company_name: e.target.value })}
            required
          />
        </label>

        <label>
          Offering description
          <textarea
            rows={8}
            value={settings.offering_description}
            onChange={(e) => setSettings({ ...settings, offering_description: e.target.value })}
            placeholder="Describe what your company sells, who it's for, and the problems it solves..."
          />
        </label>

        <div className="field-row">
          <label>
            Ingestion interval (hours)
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
            Daily digest send time
            <input
              type="time"
              value={settings.digest_send_time}
              onChange={(e) => setSettings({ ...settings, digest_send_time: e.target.value })}
            />
          </label>
        </div>
      </div>

      <div className="panel-card">
        <h2>AI configuration</h2>
        <p className="subtitle">
          Controls how Mistral is used to summarize articles — which models are called, how
          aggressively duplicate coverage is filtered, and which API key is used.
        </p>

        <div className="field-row">
          <label>
            Summarization model
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
            Triage model
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
          Pre-filter articles with the triage model before full summarization (recommended — cuts
          cost by skipping low-value articles before the expensive call)
        </label>

        <div className="field-row">
          <label>
            Embedding model (duplicate detection)
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
            Duplicate similarity threshold
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
        <p className="subtitle">
          Lower the threshold to dedupe more aggressively (more distinct stories may get merged);
          raise it to only merge near-identical coverage.
        </p>

        <label>
          Mistral API key
          <input
            type="password"
            value={apiKeyInput}
            onChange={(e) => setApiKeyInput(e.target.value)}
            placeholder="Enter a new key to set or rotate it"
            autoComplete="off"
          />
        </label>
        <p className="subtitle">{apiKeyStatusText(settings)}</p>
        {settings.mistral_api_key_source === "workspace" && (
          <button
            type="button"
            className="secondary"
            onClick={handleClearApiKeyOverride}
            disabled={isClearingKey}
          >
            {isClearingKey ? "Clearing..." : "Clear in-app override"}
          </button>
        )}
      </div>

      <button type="submit" disabled={isSaving}>
        {isSaving ? "Saving..." : "Save settings"}
      </button>
    </form>
  );
}
