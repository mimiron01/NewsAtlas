import { FormEvent, useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type {
  ArticleSource,
  NewsSourceUsageStat,
  NewsUsageSummary,
  WorkspaceSettings,
  WorkspaceSettingsUpdatePayload,
} from "../api/types";
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

function newsdataApiKeyStatusText(settings: WorkspaceSettings): string {
  if (!settings.newsdata_api_key_configured) {
    return "No API key configured — set one below or via the NEWSDATA_API_KEY environment variable.";
  }
  const suffix = settings.newsdata_api_key_last4 ? ` ending in ...${settings.newsdata_api_key_last4}` : "";
  return settings.newsdata_api_key_source === "workspace"
    ? `Using an in-app key${suffix}.`
    : `Using a key from the server's environment variable${suffix}.`;
}

// Answers "admin users can see the usage logs in the settings page" directly in this
// panel — no separate report page — showing how close a source is to the enforced
// limit configured right above it, plus its recent activity.
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

export default function SettingsProfile() {
  usePageTitle("Company profile");
  const { showToast } = useToast();
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [newsUsage, setNewsUsage] = useState<NewsUsageSummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isClearingKey, setIsClearingKey] = useState(false);
  const [isClearingNewsdataKey, setIsClearingNewsdataKey] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [newsdataApiKeyInput, setNewsdataApiKeyInput] = useState("");

  function loadNewsUsage() {
    api.get<NewsUsageSummary>("/news-usage").then(setNewsUsage).catch(() => undefined);
  }

  useEffect(() => {
    api
      .get<WorkspaceSettings>("/settings")
      .then(setSettings)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Failed to load settings"));
    loadNewsUsage();
  }, []);

  function usageFor(source: ArticleSource): NewsSourceUsageStat | undefined {
    return newsUsage?.sources.find((s) => s.source === source);
  }

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
      newsapi_enabled: settings.newsapi_enabled,
      newsapi_max_requests_per_day: settings.newsapi_max_requests_per_day,
      google_news_rss_enabled: settings.google_news_rss_enabled,
      google_news_rss_country: settings.google_news_rss_country,
      google_news_rss_language: settings.google_news_rss_language,
      google_news_rss_max_requests_per_minute: settings.google_news_rss_max_requests_per_minute,
      newsdata_enabled: settings.newsdata_enabled,
      newsdata_full_content_enabled: settings.newsdata_full_content_enabled,
      newsdata_use_native_dedupe: settings.newsdata_use_native_dedupe,
      newsdata_backfill_days: settings.newsdata_backfill_days,
      newsdata_max_requests_per_day: settings.newsdata_max_requests_per_day,
      newsdata_max_requests_per_minute: settings.newsdata_max_requests_per_minute,
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
      if (newsdataApiKeyInput.trim() !== "") {
        payload.newsdata_api_key = newsdataApiKeyInput.trim();
      }
      const updated = await api.put<WorkspaceSettings>("/settings", payload);
      setSettings(updated);
      setApiKeyInput("");
      setNewsdataApiKeyInput("");
      showToast("Settings saved.", "success");
      loadNewsUsage();
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

  async function handleClearNewsdataApiKeyOverride() {
    if (!settings) return;
    setIsClearingNewsdataKey(true);
    try {
      const updated = await api.put<WorkspaceSettings>("/settings", {
        ...basePayload(settings),
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
