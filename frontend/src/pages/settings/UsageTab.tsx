import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../../api/client";
import type { AIUsageSummary } from "../../api/types";
import Skeleton from "../../components/Skeleton";
import { useLocaleFormat } from "../../hooks/useLocaleFormat";

export default function UsageTab() {
  const { t } = useTranslation("settings");
  const { formatNumber } = useLocaleFormat();
  const [summary, setSummary] = useState<AIUsageSummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<AIUsageSummary>("/ai-usage/summary?days=30")
      .then(setSummary)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("usage.loadFailed")));
  }, [t]);

  if (loadError) {
    return <p className="error-text">{loadError}</p>;
  }

  if (!summary) {
    return (
      <div className="panel-card">
        <Skeleton rows={4} />
      </div>
    );
  }

  return (
    <div>
      <div className="panel-card">
        <h2>{t("usage.title")}</h2>
        <p className="subtitle">{t("usage.subtitle", { days: summary.period_days })}</p>
        <div className="usage-totals">
          <div>
            <strong>{summary.total_calls}</strong>
            <span>{t("usage.apiCalls")}</span>
          </div>
          <div>
            <strong>{formatNumber(summary.total_tokens)}</strong>
            <span>{t("usage.totalTokens")}</span>
          </div>
          <div>
            <strong>{formatNumber(summary.prompt_tokens)}</strong>
            <span>{t("usage.promptTokens")}</span>
          </div>
          <div>
            <strong>{formatNumber(summary.completion_tokens)}</strong>
            <span>{t("usage.completionTokens")}</span>
          </div>
        </div>
      </div>

      <div className="panel-card">
        <h3>{t("usage.byStage")}</h3>
        {summary.by_call_type.length === 0 ? (
          <p className="subtitle">{t("usage.noCallsYet")}</p>
        ) : (
          <table className="usage-table">
            <thead>
              <tr>
                <th>{t("usage.stage")}</th>
                <th>{t("usage.calls")}</th>
                <th>{t("usage.totalTokens")}</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_call_type.map((row) => (
                <tr key={row.call_type}>
                  <td>{t(`usage.callTypes.${row.call_type}`, { defaultValue: row.call_type })}</td>
                  <td>{row.call_count}</td>
                  <td>{formatNumber(row.total_tokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel-card">
        <h3>{t("usage.byCompany")}</h3>
        {summary.by_target_company.length === 0 ? (
          <p className="subtitle">{t("usage.noCallsYet")}</p>
        ) : (
          <table className="usage-table">
            <thead>
              <tr>
                <th>{t("usage.targetCompany")}</th>
                <th>{t("usage.totalTokens")}</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_target_company.map((row) => (
                <tr key={row.target_company_id ?? "unknown"}>
                  <td>{row.target_company_name ?? t("usage.deletedCompany")}</td>
                  <td>{formatNumber(row.total_tokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
