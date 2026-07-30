import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError, api } from "../../api/client";
import type { QueryPreviewResponse } from "../../api/types";
import TagInput from "../../components/TagInput";
import { useToast } from "../../context/ToastContext";

/**
 * Runs one real Google News search against a provisional configuration and shows what
 * came back, spending no AI budget and writing nothing.
 *
 * This exists because every tuning decision about terms, allowlists and editions was
 * otherwise unfalsifiable: you changed a setting, waited for the next fetch run, and
 * guessed from the signals that did or didn't appear.
 */
export default function QueryPreviewPanel() {
  const { t } = useTranslation("settings");
  const { showToast } = useToast();
  const [name, setName] = useState("");
  const [aliases, setAliases] = useState<string[]>([]);
  const [contextTerms, setContextTerms] = useState<string[]>([]);
  const [exclusionTerms, setExclusionTerms] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<QueryPreviewResponse | null>(null);

  async function handleRun() {
    setIsRunning(true);
    try {
      const response = await api.post<QueryPreviewResponse>(
        "/news-diagnostics/google-news/preview",
        {
          name: name.trim() || null,
          aliases,
          context_terms: contextTerms,
          exclusion_terms: exclusionTerms,
        }
      );
      setResult(response);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("saveFailed"), "error");
    } finally {
      setIsRunning(false);
    }
  }

  const keptCount = result?.entries.filter((entry) => entry.outcome === "kept").length ?? 0;

  return (
    <section className="settings-section">
      <h3>{t("sources.preview.title")}</h3>
      <p className="field-hint">{t("sources.preview.hint")}</p>

      <label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("sources.preview.namePlaceholder")}
          maxLength={255}
        />
      </label>
      <div className="field-row">
        <label>
          {t("targets.aliases")}
          <TagInput tags={aliases} onChange={setAliases} placeholder={t("targets.aliasesPlaceholder")} />
        </label>
        <label>
          {t("targets.contextTerms")}
          <TagInput
            tags={contextTerms}
            onChange={setContextTerms}
            placeholder={t("targets.contextTermsPlaceholder")}
          />
        </label>
        <label>
          {t("targets.exclusionTerms")}
          <TagInput
            tags={exclusionTerms}
            onChange={setExclusionTerms}
            placeholder={t("targets.exclusionTermsPlaceholder")}
          />
        </label>
      </div>

      <button type="button" onClick={handleRun} disabled={isRunning}>
        {isRunning ? t("sources.preview.running") : t("sources.preview.run")}
      </button>

      {result && (
        <div className="query-preview-result">
          <p>
            <strong>{t("sources.preview.resultQuery")}:</strong> <code>{result.query_text}</code>
          </p>
          {result.truncated && (
            <p className="error-text">{t("sources.preview.truncated")}</p>
          )}
          <p className="field-hint">
            {t("sources.preview.resultCounts", { raw: result.entries_raw, kept: keptCount })}
          </p>
          {result.entries.length === 0 ? (
            <p className="field-hint">{t("sources.preview.empty")}</p>
          ) : (
            <ul className="query-preview-entries">
              {result.entries.map((entry) => (
                <li key={entry.url} className={entry.outcome === "kept" ? "" : "muted"}>
                  <a href={entry.url} target="_blank" rel="noreferrer">
                    {entry.title}
                  </a>
                  <span className="field-hint">
                    {entry.source_name} ·{" "}
                    {entry.outcome === "kept"
                      ? t("sources.preview.outcomeKept")
                      : t("sources.preview.outcomeNotGrounded")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
