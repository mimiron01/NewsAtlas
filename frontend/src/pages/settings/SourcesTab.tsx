import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api } from "../../api/client";
import { ARTICLE_SOURCE_LABELS } from "../../api/types";
import type { ArticleSource, NewsSourceUsageStat, WorkspaceSettings } from "../../api/types";
import Skeleton from "../../components/Skeleton";
import TagInput from "../../components/TagInput";
import { useToast } from "../../context/ToastContext";
import { useLocaleFormat } from "../../hooks/useLocaleFormat";
import QueryPreviewPanel from "./QueryPreviewPanel";
import SourcePrecisionPanel from "./SourcePrecisionPanel";
import { useSettingsContext } from "./SettingsLayout";
import { buildSettingsPayload } from "./settingsPayload";

function newsdataApiKeyStatusText(settings: WorkspaceSettings, t: (key: string, options?: Record<string, unknown>) => string): string {
  if (!settings.newsdata_api_key_configured) {
    return t("sources.noApiKeyConfigured", { envVar: "NEWSDATA_API_KEY" });
  }
  const suffix = settings.newsdata_api_key_last4
    ? t("sources.endingIn", { last4: settings.newsdata_api_key_last4 })
    : "";
  return settings.newsdata_api_key_source === "workspace"
    ? t("sources.usingInAppKey", { suffix })
    : t("sources.usingEnvKey", { suffix });
}

// Shows how close a source is to the enforced limit configured right above it, plus its
// recent activity, directly in this panel — no separate report page needed.
function UsageSummary({ stat }: { stat: NewsSourceUsageStat | undefined }) {
  const { t } = useTranslation("settings");
  const { formatDate } = useLocaleFormat();
  if (!stat || !stat.enabled) return null;

  const parts: string[] = [];
  if (stat.requests_per_day_limit !== null) {
    parts.push(t("sources.requestsToday", { used: stat.requests_today, limit: stat.requests_per_day_limit }));
  }
  if (stat.requests_per_minute_limit !== null) {
    parts.push(
      t("sources.requestsLastMinute", {
        used: stat.requests_last_minute,
        limit: stat.requests_per_minute_limit,
      })
    );
  }

  return (
    <div className="news-usage-summary">
      <p className="field-hint">
        {parts.join(" · ") || t("sources.noUsageYet")}
        {stat.rate_limited_last_24h > 0 && (
          <>
            {" "}
            · <span className="error-text">{t("sources.rateLimitedCount", { count: stat.rate_limited_last_24h })}</span>
          </>
        )}
      </p>
      {stat.recent.length > 0 && (
        <details>
          <summary className="field-hint">{t("sources.recentActivity", { count: stat.recent.length })}</summary>
          <table className="news-usage-table">
            <thead>
              <tr>
                <th>{t("sources.table.when")}</th>
                <th>{t("sources.table.type")}</th>
                <th>{t("sources.table.attributedTo")}</th>
                <th>{t("sources.table.requests")}</th>
                <th>{t("sources.table.articles")}</th>
                <th>{t("sources.table.query")}</th>
              </tr>
            </thead>
            <tbody>
              {stat.recent.map((entry, idx) => (
                <tr key={idx}>
                  <td>{formatDate(entry.created_at, { dateStyle: "short", timeStyle: "short" })}</td>
                  <td>{entry.call_type}</td>
                  {/* A call is made for a company or for a topic — labelled so a topic's
                      Google News usage isn't an unattributed blank row. */}
                  <td>
                    {entry.theme_watch_name
                      ? t("sources.table.themeAttribution", { name: entry.theme_watch_name })
                      : (entry.target_company_name ?? "—")}
                  </td>
                  <td>{entry.requests_used}</td>
                  <td>
                    {entry.articles_returned}
                    {entry.articles_raw > entry.articles_returned && (
                      <span className="field-hint"> / {entry.articles_raw}</span>
                    )}
                  </td>
                  <td className="usage-query-cell">
                    {entry.query_text && <code title={entry.query_text}>{entry.query_text}</code>}
                    {entry.drop_counts && Object.keys(entry.drop_counts).length > 0 && (
                      <span className="field-hint">
                        {Object.entries(entry.drop_counts)
                          .filter(([, count]) => count > 0)
                          .map(([stage, count]) => `${stage}: ${count}`)
                          .join(" · ")}
                      </span>
                    )}
                  </td>
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
  const { t } = useTranslation("settings");
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
      showToast(t("saved"), "success");
      reloadNewsUsage();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("saveFailed"), "error");
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
      showToast(t("sources.clearNewsdataKeyToast"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("sources.clearNewsdataKeyFailed"), "error");
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
        <h2>{t("sources.title")}</h2>
        <p className="subtitle">{t("sources.subtitle")}</p>

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
            {t("sources.maxRequestsPerDay")}
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
          <p className="field-hint">{t("sources.googleNewsRss.hint")}</p>
          {settings.google_news_rss_enabled && (
            <div className="field-row">
              <label>
                {t("sources.googleNewsRss.country")}
                <input
                  value={settings.google_news_rss_country}
                  onChange={(e) =>
                    setSettings({ ...settings, google_news_rss_country: e.target.value.toUpperCase() })
                  }
                  maxLength={8}
                />
              </label>
              <label>
                {t("sources.googleNewsRss.language")}
                <input
                  value={settings.google_news_rss_language}
                  onChange={(e) =>
                    setSettings({ ...settings, google_news_rss_language: e.target.value.toLowerCase() })
                  }
                  maxLength={8}
                />
              </label>
              <label>
                {t("sources.maxRequestsPerMinute")}
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
              <label>
                {t("sources.googleNewsRss.sourceAllowlist")}
                <TagInput
                  tags={settings.google_news_source_allowlist}
                  onChange={(tags) => setSettings({ ...settings, google_news_source_allowlist: tags })}
                  placeholder={t("sources.googleNewsRss.sourceAllowlistPlaceholder")}
                />
                <span className="field-hint">{t("sources.googleNewsRss.sourceAllowlistHint")}</span>
              </label>
              <label>
                {t("sources.googleNewsRss.sourceDenylist")}
                <TagInput
                  tags={settings.google_news_source_denylist}
                  onChange={(tags) => setSettings({ ...settings, google_news_source_denylist: tags })}
                  placeholder={t("sources.googleNewsRss.sourceDenylistPlaceholder")}
                />
                <span className="field-hint">{t("sources.googleNewsRss.sourceDenylistHint")}</span>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={settings.google_news_time_operator_enabled}
                  onChange={(e) =>
                    setSettings({ ...settings, google_news_time_operator_enabled: e.target.checked })
                  }
                />
                {t("sources.googleNewsRss.timeOperator")}
              </label>
              <span className="field-hint">{t("sources.googleNewsRss.timeOperatorHint")}</span>
              <label>
                {t("sources.googleNewsRss.queryStrategy")}
                <select
                  value={settings.google_news_query_strategy}
                  onChange={(e) =>
                    setSettings({ ...settings, google_news_query_strategy: e.target.value })
                  }
                >
                  <option value="single">{t("sources.googleNewsRss.queryStrategySingle")}</option>
                  <option value="split">{t("sources.googleNewsRss.queryStrategySplit")}</option>
                </select>
                <span className="field-hint">{t("sources.googleNewsRss.queryStrategyHint")}</span>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={settings.google_news_resolve_urls_enabled}
                  onChange={(e) =>
                    setSettings({ ...settings, google_news_resolve_urls_enabled: e.target.checked })
                  }
                />
                {t("sources.googleNewsRss.resolveUrls")}
              </label>
              <span className="field-hint">{t("sources.googleNewsRss.resolveUrlsHint")}</span>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={settings.google_news_fetch_snippets_enabled}
                  // Snippet fetching needs a resolved publisher URL to fetch from, so the
                  // two toggles aren't independent — enabling this enables that.
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      google_news_fetch_snippets_enabled: e.target.checked,
                      google_news_resolve_urls_enabled:
                        e.target.checked || settings.google_news_resolve_urls_enabled,
                    })
                  }
                />
                {t("sources.googleNewsRss.fetchSnippets")}
              </label>
              <span className="field-hint">{t("sources.googleNewsRss.fetchSnippetsHint")}</span>
              {settings.google_news_fetch_snippets_enabled && (
                <div className="field-row">
                  <label>
                    {t("sources.googleNewsRss.enrichmentFetches")}
                    <input
                      type="number"
                      min={0}
                      value={settings.max_enrichment_fetches_per_run}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          max_enrichment_fetches_per_run: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                  <label>
                    {t("sources.googleNewsRss.enrichmentSeconds")}
                    <input
                      type="number"
                      min={0}
                      value={settings.max_enrichment_seconds_per_run}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          max_enrichment_seconds_per_run: Number(e.target.value),
                        })
                      }
                    />
                  </label>
                </div>
              )}
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
          <p className="field-hint">{t("sources.newsdata.hint")}</p>
          {settings.newsdata_enabled && (
            <>
              <div className="field-row">
                <label>
                  {t("sources.maxRequestsPerDay")}
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
                  {t("sources.maxRequestsPerMinute")}
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
                {t("sources.newsdata.fetchFullContent")}
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={settings.newsdata_use_native_dedupe}
                  onChange={(e) =>
                    setSettings({ ...settings, newsdata_use_native_dedupe: e.target.checked })
                  }
                />
                {t("sources.newsdata.useNativeDedupe")}
              </label>
              <label>
                {t("sources.newsdata.backfillWindow")}
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
              <p className="field-hint">{t("sources.newsdata.backfillHint")}</p>

              <label>
                {t("sources.newsdata.apiKey")}
                <input
                  type="password"
                  value={newsdataApiKeyInput}
                  onChange={(e) => setNewsdataApiKeyInput(e.target.value)}
                  placeholder={t("sources.newsdata.apiKeyPlaceholder")}
                  autoComplete="off"
                />
              </label>
              <p className="field-hint">{newsdataApiKeyStatusText(settings, t)}</p>
              {settings.newsdata_api_key_source === "workspace" && (
                <button
                  type="button"
                  className="secondary"
                  onClick={handleClearNewsdataApiKeyOverride}
                  disabled={isClearingNewsdataKey}
                >
                  {isClearingNewsdataKey ? t("clearing") : t("clearOverride")}
                </button>
              )}
            </>
          )}
          <UsageSummary stat={usageFor("newsdata")} />
        </div>

        <div className="news-source-row">
          <strong>{t("sources.googleNewsRss.themeSources")}</strong>
          <p className="field-hint">{t("sources.googleNewsRss.themeSourcesHint")}</p>
          <div className="field-row">
            {(["google_news_rss", "newsapi", "newsdata"] as ArticleSource[]).map((source) => (
              <label key={source} className="checkbox-label">
                <input
                  type="checkbox"
                  checked={settings.theme_news_sources.includes(source)}
                  onChange={(e) =>
                    setSettings({
                      ...settings,
                      theme_news_sources: e.target.checked
                        ? [...settings.theme_news_sources, source]
                        : settings.theme_news_sources.filter((s) => s !== source),
                    })
                  }
                />
                {ARTICLE_SOURCE_LABELS[source]}
              </label>
            ))}
          </div>
          <label>
            {t("sources.googleNewsRss.themeRequestBudget")}
            <input
              type="number"
              min={0}
              value={settings.max_theme_requests_per_run_per_source}
              onChange={(e) =>
                setSettings({
                  ...settings,
                  max_theme_requests_per_run_per_source: Number(e.target.value),
                })
              }
            />
            <span className="field-hint">{t("sources.googleNewsRss.themeRequestBudgetHint")}</span>
          </label>
        </div>
      </div>

      <button type="submit" disabled={isSaving}>
        {isSaving ? t("saving") : t("save")}
      </button>

      {/* Advisory panels, below the save button: neither edits settings directly, and the
          precision one writes into the denylist above rather than saving on its own, so
          the admin still reviews the change before it takes effect. */}
      <QueryPreviewPanel />
      <SourcePrecisionPanel
        blockedDomains={settings.google_news_source_denylist}
        onBlockDomain={(domain) =>
          setSettings({
            ...settings,
            google_news_source_denylist: [...settings.google_news_source_denylist, domain],
          })
        }
      />
    </form>
  );
}
