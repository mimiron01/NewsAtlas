import { useEffect, useState } from "react";

import { api, ApiError } from "../../api/client";
import type { AIUsageSummary } from "../../api/types";
import Skeleton from "../../components/Skeleton";

const CALL_TYPE_LABELS: Record<string, string> = {
  embedding: "Duplicate detection (embeddings)",
  triage: "Relevance triage (small model)",
  summarize: "Full summarization (large model)",
};

export default function UsageTab() {
  const [summary, setSummary] = useState<AIUsageSummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<AIUsageSummary>("/ai-usage/summary?days=30")
      .then(setSummary)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Failed to load AI usage"));
  }, []);

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
        <h2>AI usage</h2>
        <p className="subtitle">
          Mistral token usage over the last {summary.period_days} days, broken down by pipeline
          stage so you can see the cost impact of duplicate-skipping and triage filtering.
        </p>
        <div className="usage-totals">
          <div>
            <strong>{summary.total_calls}</strong>
            <span>API calls</span>
          </div>
          <div>
            <strong>{summary.total_tokens.toLocaleString()}</strong>
            <span>Total tokens</span>
          </div>
          <div>
            <strong>{summary.prompt_tokens.toLocaleString()}</strong>
            <span>Prompt tokens</span>
          </div>
          <div>
            <strong>{summary.completion_tokens.toLocaleString()}</strong>
            <span>Completion tokens</span>
          </div>
        </div>
      </div>

      <div className="panel-card">
        <h3>By pipeline stage</h3>
        {summary.by_call_type.length === 0 ? (
          <p className="subtitle">No AI calls recorded yet.</p>
        ) : (
          <table className="usage-table">
            <thead>
              <tr>
                <th>Stage</th>
                <th>Calls</th>
                <th>Total tokens</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_call_type.map((row) => (
                <tr key={row.call_type}>
                  <td>{CALL_TYPE_LABELS[row.call_type] ?? row.call_type}</td>
                  <td>{row.call_count}</td>
                  <td>{row.total_tokens.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="panel-card">
        <h3>By target company</h3>
        {summary.by_target_company.length === 0 ? (
          <p className="subtitle">No AI calls recorded yet.</p>
        ) : (
          <table className="usage-table">
            <thead>
              <tr>
                <th>Target company</th>
                <th>Total tokens</th>
              </tr>
            </thead>
            <tbody>
              {summary.by_target_company.map((row) => (
                <tr key={row.target_company_id ?? "unknown"}>
                  <td>{row.target_company_name ?? "(deleted target company)"}</td>
                  <td>{row.total_tokens.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
