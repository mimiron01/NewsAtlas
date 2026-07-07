import { useEffect, useState } from "react";

import { api, ApiError } from "../../api/client";
import { ARTICLE_SOURCE_LABELS } from "../../api/types";
import type { IngestionRunStatus } from "../../api/types";
import Skeleton from "../../components/Skeleton";

const STATUS_LABELS: Record<IngestionRunStatus["status"], string> = {
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};

const STATUS_CLASSES: Record<IngestionRunStatus["status"], string> = {
  running: "status-new",
  completed: "status-reviewed",
  failed: "status-dismissed",
};

const TRIGGER_LABELS: Record<IngestionRunStatus["trigger"], string> = {
  manual: "Manual",
  scheduled: "Scheduled",
};

function formatDuration(startedAt: string, finishedAt: string | null): string {
  if (!finishedAt) return "";
  const seconds = Math.max(0, (new Date(finishedAt).getTime() - new Date(startedAt).getTime()) / 1000);
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.round(seconds / 60)}m`;
}

export default function LogsTab() {
  const [runs, setRuns] = useState<IngestionRunStatus[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<IngestionRunStatus[]>("/ingestion/runs?limit=50")
      .then(setRuns)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Failed to load logs"));
  }, []);

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
      <h2>Ingestion logs</h2>
      <p className="subtitle">
        History of every "Fetch new signals" run, manual or scheduled, including any errors
        encountered while pulling from a news source or summarizing an article.
      </p>

      {runs.length === 0 && <p className="subtitle">No ingestion runs yet.</p>}

      <ul className="target-list">
        {runs.map((run) => {
          const hasIssues = run.errors.length > 0 || run.fatal_error !== null;
          return (
            <li key={run.id}>
              <div>
                <span className={`status-badge ${STATUS_CLASSES[run.status]}`}>
                  {STATUS_LABELS[run.status]}
                </span>{" "}
                <strong>{new Date(run.started_at).toLocaleString()}</strong>
                <span className="tag">{TRIGGER_LABELS[run.trigger]}</span>
                {run.finished_at && <span className="tag">{formatDuration(run.started_at, run.finished_at)}</span>}
                <div className="keywords">
                  {run.companies_processed}/{run.companies_total} compan
                  {run.companies_total === 1 ? "y" : "ies"} · {run.articles_fetched} article(s) fetched ·{" "}
                  {run.articles_new} new · {run.signals_created} signal(s) created
                  {(run.duplicates_skipped > 0 || run.triaged_out > 0) && (
                    <> · {run.duplicates_skipped} duplicate(s), {run.triaged_out} triaged out</>
                  )}
                </div>
                {Object.keys(run.by_source).length > 0 && (
                  <div className="field-hint">
                    By source:{" "}
                    {Object.entries(run.by_source)
                      .map(
                        ([source, count]) =>
                          `${ARTICLE_SOURCE_LABELS[source as keyof typeof ARTICLE_SOURCE_LABELS] ?? source}: ${count}`
                      )
                      .join(", ")}
                  </div>
                )}
                {run.fatal_error && <p className="error-text">Run crashed: {run.fatal_error}</p>}
                {hasIssues && run.errors.length > 0 && (
                  <details>
                    <summary className="field-hint error-text">
                      {run.errors.length} error{run.errors.length === 1 ? "" : "s"}
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
