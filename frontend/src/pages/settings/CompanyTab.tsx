import { FormEvent, useState } from "react";

import { ApiError, api } from "../../api/client";
import type { WorkspaceSettings } from "../../api/types";
import Skeleton from "../../components/Skeleton";
import { useToast } from "../../context/ToastContext";
import { useSettingsContext } from "./SettingsLayout";
import { buildSettingsPayload } from "./settingsPayload";

export default function CompanyTab() {
  const { showToast } = useToast();
  const { settings, setSettings, loadError } = useSettingsContext();
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setIsSaving(true);
    try {
      const updated = await api.put<WorkspaceSettings>("/settings", buildSettingsPayload(settings));
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

        <label>
          Main language
          <select
            value={settings.main_language}
            onChange={(e) =>
              setSettings({ ...settings, main_language: e.target.value as "en" | "de" })
            }
          >
            <option value="en">English</option>
            <option value="de">Deutsch</option>
          </select>
          <span className="field-hint">
            The standard language for the interface and AI-generated signal summaries. Users can
            still override it for themselves in their own profile.
          </span>
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

      <button type="submit" disabled={isSaving}>
        {isSaving ? "Saving..." : "Save settings"}
      </button>
    </form>
  );
}
