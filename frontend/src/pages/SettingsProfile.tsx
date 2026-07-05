import { FormEvent, useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { WorkspaceSettings } from "../api/types";
import Skeleton from "../components/Skeleton";
import { useToast } from "../context/ToastContext";
import { usePageTitle } from "../hooks/usePageTitle";

export default function SettingsProfile() {
  usePageTitle("Company profile");
  const { showToast } = useToast();
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    api
      .get<WorkspaceSettings>("/settings")
      .then(setSettings)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Failed to load settings"));
  }, []);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setIsSaving(true);
    try {
      const updated = await api.put<WorkspaceSettings>("/settings", {
        company_name: settings.company_name,
        offering_description: settings.offering_description,
        digest_send_time: settings.digest_send_time,
        ingestion_interval_hours: settings.ingestion_interval_hours,
      });
      setSettings(updated);
      showToast("Settings saved.", "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to save settings", "error");
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
    <form className="panel-card" onSubmit={handleSubmit}>
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

      <button type="submit" disabled={isSaving}>
        {isSaving ? "Saving..." : "Save settings"}
      </button>
    </form>
  );
}
