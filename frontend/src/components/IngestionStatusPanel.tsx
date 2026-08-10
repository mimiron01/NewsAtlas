import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ARTICLE_SOURCE_LABELS } from "../api/types";
import type { IngestionRunStatus } from "../api/types";
import { useLocaleFormat } from "../hooks/useLocaleFormat";

interface IngestionStatusPanelProps {
  status: IngestionRunStatus | null;
  isAdmin: boolean;
  onCancel?: () => void;
}

function ingestionStatusText(
  t: ReturnType<typeof useTranslation>["t"],
  status: IngestionRunStatus
): string {
  if (status.status === "failed") {
    return status.fatal_error
      ? t("feed.ingestion.failedWithReason", { reason: status.fatal_error })
      : t("feed.ingestion.failed");
  }
  if (status.status === "completed") {
    return t("feed.ingestion.finishingUp");
  }
  if (status.status === "cancelled") {
    return t("feed.ingestion.cancelledProgress", {
      processed: status.companies_processed,
      total: status.companies_total,
    });
  }
  if (status.cancel_requested) {
    return t("feed.ingestion.stopping");
  }
  const companyPosition = Math.min(status.companies_processed + 1, Math.max(status.companies_total, 1));
  const companyProgress =
    status.companies_total > 0
      ? t("feed.ingestion.companyProgress", { position: companyPosition, total: status.companies_total })
      : "";
  if (status.current_step === "summarizing" && status.articles_total_this_company > 0) {
    const articlePosition = Math.min(
      status.articles_processed_this_company + 1,
      status.articles_total_this_company
    );
    return t("feed.ingestion.summarizing", {
      company: status.current_company_name ?? t("feed.ingestion.defaultCompanyName"),
      article: articlePosition,
      total: status.articles_total_this_company,
      companyProgress,
    });
  }
  if (status.current_step === "waiting") {
    return t("feed.ingestion.waitingForRateLimit", {
      company: status.current_theme_name ?? status.current_company_name ?? t("feed.ingestion.defaultCompanyName"),
      companyProgress,
    });
  }
  // The theme phase runs after every company, and clears current_company_name when it
  // starts — without this branch the UI kept naming the last company processed while it
  // was really working through topics.
  if (status.current_theme_name) {
    return t("feed.ingestion.fetchingTheme", {
      theme: status.current_theme_name,
      position: Math.min(status.themes_processed + 1, Math.max(status.themes_total, 1)),
      total: Math.max(status.themes_total, 1),
    });
  }
  if (status.current_company_name) {
    return t("feed.ingestion.fetching", { company: status.current_company_name, companyProgress });
  }
  return t("feed.ingestion.starting");
}

/** Live progress bar while a run (manual or scheduled) is in flight, or a persistent
 * "last run" summary once it's settled — shown regardless of whether this page load
 * actually watched the run happen, so returning to the page later still reflects
 * reality instead of going blank. */
export default function IngestionStatusPanel({ status, isAdmin, onCancel }: IngestionStatusPanelProps) {
  const { t } = useTranslation("signals");
  const { formatDate } = useLocaleFormat();

  if (!status) return null;

  const nonDuplicateNewCount = status.articles_new - status.duplicates_skipped;
  const triageSkipRate = nonDuplicateNewCount > 0 ? status.triaged_out / nonDuplicateNewCount : 0;
  const showHighSkipRateWarning =
    isAdmin && status.status === "completed" && nonDuplicateNewCount >= 3 && triageSkipRate >= 0.7;
  const issueCount = status.errors.length + (status.fatal_error ? 1 : 0);
  const hasIssues = issueCount > 0;
  const lastRunTime = formatDate(status.finished_at ?? status.started_at, {
    dateStyle: "short",
    timeStyle: "short",
  });

  if (status.status === "running") {
    return (
      <div className="panel-card">
        <div className="progress-bar">
          <div className="progress-bar-fill" style={{ width: `${status.progress_percent}%` }} />
        </div>
        <div className="ingestion-progress-row">
          <p className="field-hint">{ingestionStatusText(t, status)}</p>
          {isAdmin && onCancel && (
            <button
              type="button"
              className="danger"
              onClick={onCancel}
              disabled={status.cancel_requested}
            >
              {status.cancel_requested ? t("feed.ingestion.stopping") : t("feed.ingestion.stop")}
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="panel-card">
      <p className="field-hint">
        {t("feed.ingestion.lastRunAt", { time: lastRunTime })}
        {" · "}
        {hasIssues
          ? t("feed.ingestion.issuesCount", { count: issueCount })
          : t("feed.ingestion.noIssues")}
      </p>

      {status.status === "failed" && <p className="error-text">{ingestionStatusText(t, status)}</p>}

      {status.status === "cancelled" && (
        <p className="subtitle">
          {t("feed.ingestion.cancelledProgress", {
            processed: status.companies_processed,
            total: status.companies_total,
          })}
          {t("feed.ingestion.articlesFound", { count: status.articles_new })}
          {t("feed.ingestion.signalsCreatedText", { count: status.signals_created })}.
        </p>
      )}

      {status.status === "completed" && (
        <>
          <p className="subtitle">
            {t("feed.ingestion.companiesChecked", { count: status.companies_total })}
            {/* Only mentioned once topics are actually part of the run, so a company-only
                workspace's summary reads exactly as it did before. */}
            {status.themes_total > 0 && t("feed.ingestion.themesChecked", { count: status.themes_total })}
            {t("feed.ingestion.articlesFound", { count: status.articles_new })}
            {t("feed.ingestion.signalsCreatedText", { count: status.signals_created })}
            {status.themes_total > 0 &&
              t("feed.ingestion.themeMatchesCreatedText", { count: status.theme_matches_created })}
            {(status.duplicates_skipped > 0 || status.triaged_out > 0) && (
              <>
                {" "}
                {t("feed.ingestion.skippedSuffix", {
                  duplicates: t("feed.ingestion.duplicatesSkipped", { count: status.duplicates_skipped }),
                  lowRelevance: t("feed.ingestion.lowRelevanceSkipped", { count: status.triaged_out }),
                })}
              </>
            )}
            .
          </p>
          {showHighSkipRateWarning && (
            <p className="field-hint error-text">
              {t("feed.ingestion.highSkipRateWarning", { percent: Math.round(triageSkipRate * 100) })}{" "}
              <Link to="/skipped">{t("feed.ingestion.reviewSkippedArticles")}</Link>
            </p>
          )}
          {Object.keys(status.by_source).length > 0 && (
            <p className="field-hint">
              {t("feed.bySource")}{" "}
              {Object.entries(status.by_source)
                .map(([source, count]) => `${ARTICLE_SOURCE_LABELS[source as keyof typeof ARTICLE_SOURCE_LABELS] ?? source}: ${count}`)
                .join(", ")}
            </p>
          )}
        </>
      )}

      {Object.keys(status.rate_limited).length > 0 && (
        <p className="field-hint error-text">
          {t("feed.rateLimited")}{" "}
          {Object.entries(status.rate_limited)
            .map(
              ([source, count]) =>
                `${ARTICLE_SOURCE_LABELS[source as keyof typeof ARTICLE_SOURCE_LABELS] ?? source}: ${t(
                  "feed.ingestion.companiesRateLimited",
                  { count }
                )}`
            )
            .join(", ")}
        </p>
      )}
      {status.errors.length > 0 && (
        <ul className="error-list">
          {status.errors.map((message) => (
            <li key={message} className="error-text">
              {message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
