import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../../api/client";
import { ARTICLE_SOURCE_LABELS } from "../../api/types";
import type { IngestionRunStatus } from "../../api/types";
import Skeleton from "../../components/Skeleton";
import { useLocaleFormat } from "../../hooks/useLocaleFormat";

const STATUS_CLASSES: Record<IngestionRunStatus["status"], string> = {
  running: "status-new",
  completed: "status-reviewed",
  failed: "status-dismissed",
  cancelled: "status-archived",
};

function formatDuration(startedAt: string, finishedAt: string | null): string {
  if (!finishedAt) return "";
  const seconds = Math.max(0, (new Date(finishedAt).getTime() - new Date(startedAt).getTime()) / 1000);
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

export default function LogsTab() {
  const { t } = useTranslation("settings");
  const { formatDate } = useLocaleFormat();
  const [runs, setRuns] = useState<IngestionRunStatus[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<IngestionRunStatus[]>("/ingestion/runs?limit=50")
      .then(setRuns)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("logs.loadFailed")));
  }, [t]);

  if (loadError) {
    return <p className="error-text">{loadError}</p>;
  }

  if (runs === null) {
    return (
      <div className="panel-card">
        <Skeleton rows={4} />
      </div>
    );
  }

  return (
    <div className="panel-card">
      <h2>{t("logs.title")}</h2>
      <p className="subtitle">{t("logs.subtitle")}</p>

      {runs.length === 0 && <p className="subtitle">{t("logs.noRunsYet")}</p>}

      <ul className="target-list">
        {runs.map((run) => {
          const hasIssues = run.errors.length > 0 || run.fatal_error !== null;
          return (
            <li key={run.id}>
              <div>
                <span className={`status-badge ${STATUS_CLASSES[run.status]}`}>
                  {t(`logs.status.${run.status}`)}
                </span>{" "}
                <strong>{formatDate(run.started_at, { dateStyle: "short", timeStyle: "short" })}</strong>
                <span className="tag">{t(`logs.trigger.${run.trigger}`)}</span>
                {run.finished_at && <span className="tag">{formatDuration(run.started_at, run.finished_at)}</span>}
                <div className="keywords">
                  {t("logs.companiesProcessed", { processed: run.companies_processed, total: run.companies_total, count: run.companies_total })}
                  {" · "}
                  {t("logs.articlesFetched", { count: run.articles_fetched })}
                  {" · "}
                  {t("logs.newCount", { count: run.articles_new })}
                  {" · "}
                  {t("logs.signalsCreated", { count: run.signals_created })}
                  {(run.duplicates_skipped > 0 || run.triaged_out > 0) && (
                    <>
                      {" · "}
                      {t("logs.duplicatesSkipped", { count: run.duplicates_skipped })}
                      {", "}
                      {t("logs.triagedOut", { count: run.triaged_out })}
                    </>
                  )}
                </div>
                {Object.keys(run.by_source).length > 0 && (
                  <div className="field-hint">
                    {t("logs.bySource")}{" "}
                    {Object.entries(run.by_source)
                      .map(
                        ([source, count]) =>
                          `${ARTICLE_SOURCE_LABELS[source as keyof typeof ARTICLE_SOURCE_LABELS] ?? source}: ${count}`
                      )
                      .join(", ")}
                  </div>
                )}
                {run.fatal_error && (
                  <p className="error-text">{t("logs.runCrashed", { error: run.fatal_error })}</p>
                )}
                {hasIssues && run.errors.length > 0 && (
                  <details>
                    <summary className="field-hint error-text">
                      {t("logs.errorCount", { count: run.errors.length })}
                    </summary>
                    <ul className="error-list">
                      {run.errors.map((message, idx) => (
                        <li key={idx} className="error-text">
                          {message}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
