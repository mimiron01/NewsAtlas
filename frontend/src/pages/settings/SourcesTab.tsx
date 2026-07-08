import { FormEvent, useState } from "react";

import { ApiError, api } from "../../api/client";
import type { ArticleSource, NewsSourceUsageStat, WorkspaceSettings } from "../../api/types";
import Skeleton from "../../components/Skeleton";
import { useToast } from "../../context/ToastContext";
import { useSettingsContext } from "./SettingsLayout";
import { buildSettingsPayload } from "./settingsPayload";

function newsdataApiKeyStatusText(settings: WorkspaceSettings): string {
  if (!settings.newsdata_api_key_configured) {
    return "No API key configured — set one below or via the NEWSDATA_API_KEY environment variable.";
  }
  const suffix = settings.newsdata_api_key_last4 ? ` ending in ...${settings.newsdata_api_key_last4}` : "";
  return settings.newsdata_api_key_source === "workspace"
    ? `Using an in-app key${suffix}.`
    : `Using a key from the server's environment variable${suffix}.`;
}

// Shows how close a source is to the enforced limit configured right above it, plus its
// recent activity, directly in this panel — no separate report page needed.
function UsageSummary({ stat }: { stat: NewsSourceUsageStat | undefined }) {
  if (!stat || !stat.enabled) return null;

  const parts: string[] = [];
  if (stat.requests_per_day_limit !== null) {
    parts.push(`${stat.requests_today} / ${stat.requests_per_day_limit} requests today`);
  }
  if (stat.requests_per_minute_limit !== null) {
    parts.push(`${stat.requests_last_minute} / ${stat.requests_per_minute_limit} in the last minute`);
  }

  return (
    <div className="news-usage-summary">
      <p className="field-hint">
        {parts.join(" · ") || "No usage recorded yet."}
        {stat.rate_limited_last_24h > 0 && (
          <> · <span className="error-text">rate limited {stat.rate_limited_last_24h}x in the last 24h</span></>
        )}
      </p>
      {stat.recent.length > 0 && (
        <details>
          <summary className="field-hint">Recent activity ({stat.recent.length})</summary>
          <table className="news-usage-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Type</th>
                <th>Company</th>
                <th>Requests</th>
                <th>Articles</th>
              </tr>
            </thead>
            <tbody>
              {stat.recent.map((entry, idx) => (
                <tr key={idx}>
                  <td>{new Date(entry.created_at).toLocaleString()}</td>
                  <td>{entry.call_type}</td>
                  <td>{entry.target_company_name ?? "—"}</td>
                  <td>{entry.requests_used}</td>
                  <td>{entry.articles_returned}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}

export default function SourcesTab() {
  const { showToast } = useToast();
  const { settings, setSettings, loadError, newsUsage, reloadNewsUsage } = useSettingsContext();
  const [isSaving, setIsSaving] = useState(false);
  const [isClearingNewsdataKey, setIsClearingNewsdataKey] = useState(false);
  const [newsdataApiKeyInput, setNewsdataApiKeyInput] = useState("");

  function usageFor(source: ArticleSource): NewsSourceUsageStat | undefined {
    return newsUsage?.sources.find((s) => s.source === source);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!settings) return;
    setIsSaving(true);
    try {
      const payload = buildSettingsPayload(settings);
      if (newsdataApiKeyInput.trim() !== "") {
        payload.newsdata_api_key = newsdataApiKeyInput.trim();
      }
      const updated = await api.put<WorkspaceSettings>("/settings", payload);
      setSettings(updated);
      setNewsdataApiKeyInput("");
      showToast("Settings saved.", "success");
      reloadNewsUsage();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to save settings", "error");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleClearNewsdataApiKeyOverride() {
    if (!settings) return;
    setIsClearingNewsdataKey(true);
    try {
      const updated = await api.put<WorkspaceSettings>("/settings", {
        ...buildSettingsPayload(settings),
        newsdata_api_key: "",
      });
      setSettings(updated);
      setNewsdataApiKeyInput("");
      showToast("In-app NewsData.io API key override cleared.", "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to clear API key", "error");
    } finally {
      setIsClearingNewsdataKey(false);
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
        <h2>News sources</h2>
        <p className="subtitle">
          Which providers ingestion pulls from, each with its own enforced rate limit — a source
          stops being called for the rest of a run once its limit is reached, rather than only
          logging the overage afterward. Usage against each limit is shown inline below it.
        </p>

        <div className="news-source-row">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={settings.newsapi_enabled}
              onChange={(e) => setSettings({ ...settings, newsapi_enabled: e.target.checked })}
            />
            <strong>NewsAPI.org</strong>
          </label>
          <label>
            Max requests / day
            <input
              type="number"
              min={1}
              value={settings.newsapi_max_requests_per_day}
              onChange={(e) =>
                setSettings({ ...settings, newsapi_max_requests_per_day: Number(e.target.value) })
              }
            />
          </label>
          <UsageSummary stat={usageFor("newsapi")} />
        </div>

        <div className="news-source-row">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={settings.google_news_rss_enabled}
              onChange={(e) => setSettings({ ...settings, google_news_rss_enabled: e.target.checked })}
            />
            <strong>Google News RSS</strong>
          </label>
          <p className="field-hint">
            Free, keyless public feed. Google publishes no official quota for it, so the limit
            below is a self-imposed politeness ceiling, not a real plan tier.
          </p>
          {settings.google_news_rss_enabled && (
            <div className="field-row">
              <label>
                Country
                <input
                  value={settings.google_news_rss_country}
                  onChange={(e) =>
                    setSettings({ ...settings, google_news_rss_country: e.target.value.toUpperCase() })
                  }
                  maxLength={8}
                />
              </label>
              <label>
                Language
                <input
                  value={settings.google_news_rss_language}
                  onChange={(e) =>
                    setSettings({ ...settings, google_news_rss_language: e.target.value.toLowerCase() })
                  }
                  maxLength={8}
                />
              </label>
              <label>
                Max requests / minute
                <input
                  type="number"
                  min={1}
                  value={settings.google_news_rss_max_requests_per_minute}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      google_news_rss_max_requests_per_minute: Number(e.target.value),
                    })
                  }
                />
              </label>
            </div>
          )}
          <UsageSummary stat={usageFor("google_news_rss")} />
        </div>

        <div className="news-source-row">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={settings.newsdata_enabled}
              onChange={(e) => setSettings({ ...settings, newsdata_enabled: e.target.checked })}
            />
            <strong>NewsData.io</strong>
          </label>
          <p className="field-hint">
            Paid API — leans on full-article-content grounding, native duplicate removal, native
            sentiment/tags, and a one-time historical backfill when a company is added.
          </p>
          {settings.newsdata_enabled && (
            <>
              <div className="field-row">
                <label>
                  Max requests / day
                  <input
                    type="number"
                    min={1}
                    value={settings.newsdata_max_requests_per_day}
                    onChange={(e) =>
                      setSettings({ ...settings, newsdata_max_requests_per_day: Number(e.target.value) })
                    }
                  />
                </label>
                <label>
                  Max requests / minute
                  <input
                    type="number"
                    min={1}
                    value={settings.newsdata_max_requests_per_minute}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        newsdata_max_requests_per_minute: Number(e.target.value),
                      })
                    }
                  />
                </label>
              </div>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={settings.newsdata_full_content_enabled}
                  onChange={(e) =>
                    setSettings({ ...settings, newsdata_full_content_enabled: e.target.checked })
                  }
                />
                Fetch full article content when the plan includes it (better-grounded summaries)
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={settings.newsdata_use_native_dedupe}
                  onChange={(e) =>
                    setSettings({ ...settings, newsdata_use_native_dedupe: e.target.checked })
                  }
                />
                Use NewsData.io's native duplicate removal
              </label>
              <label>
                Historical backfill window (days, 0 = off)
                <input
                  type="number"
                  min={0}
                  max={1825}
                  value={settings.newsdata_backfill_days}
                  onChange={(e) =>
                    setSettings({ ...settings, newsdata_backfill_days: Number(e.target.value) })
                  }
                />
              </label>
              <p className="field-hint">
                When set, newly-created companies automatically get a one-time historical pull
                covering this many days via NewsData.io's archive endpoint.
              </p>

              <label>
                NewsData.io API key
                <input
                  type="password"
                  value={newsdataApiKeyInput}
                  onChange={(e) => setNewsdataApiKeyInput(e.target.value)}
                  placeholder="Enter a new key to set or rotate it"
                  autoComplete="off"
                />
              </label>
              <p className="field-hint">{newsdataApiKeyStatusText(settings)}</p>
              {settings.newsdata_api_key_source === "workspace" && (
                <button
                  type="button"
                  className="secondary"
                  onClick={handleClearNewsdataApiKeyOverride}
                  disabled={isClearingNewsdataKey}
                >
                  {isClearingNewsdataKey ? "Clearing..." : "Clear in-app override"}
                </button>
              )}
            </>
          )}
          <UsageSummary stat={usageFor("newsdata")} />
        </div>
      </div>

      <button type="submit" disabled={isSaving}>
        {isSaving ? "Saving..." : "Save settings"}
      </button>
    </form>
  );
}
