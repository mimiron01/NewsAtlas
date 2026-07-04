import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiError } from "../api/client";
import type { IngestionRunResult, Signal, SignalStatus, TargetCompany } from "../api/types";

const STATUS_OPTIONS: { value: SignalStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "new", label: "New" },
  { value: "reviewed", label: "Reviewed" },
  { value: "archived", label: "Archived" },
  { value: "dismissed", label: "Dismissed" },
];

export default function SignalsFeed() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [companyFilter, setCompanyFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<SignalStatus | "">("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRunningIngestion, setIsRunningIngestion] = useState(false);
  const [ingestionResult, setIngestionResult] = useState<IngestionRunResult | null>(null);

  function loadSignals() {
    setIsLoading(true);
    const params = new URLSearchParams();
    if (companyFilter) params.set("company_id", companyFilter);
    if (statusFilter) params.set("status", statusFilter);
    const query = params.toString();
    api
      .get<Signal[]>(`/signals${query ? `?${query}` : ""}`)
      .then(setSignals)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load signals"))
      .finally(() => setIsLoading(false));
  }

  useEffect(() => {
    api.get<TargetCompany[]>("/target-companies").then(setCompanies).catch(() => undefined);
  }, []);

  useEffect(loadSignals, [companyFilter, statusFilter]);

  async function handleRunIngestion() {
    setError(null);
    setIngestionResult(null);
    setIsRunningIngestion(true);
    try {
      const result = await api.post<IngestionRunResult>("/ingestion/run-now");
      setIngestionResult(result);
      loadSignals();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ingestion run failed");
    } finally {
      setIsRunningIngestion(false);
    }
  }

  return (
    <div>
      <div className="panel-card feed-toolbar">
        <div>
          <h2>Signals feed</h2>
          <p className="subtitle">News signals for your target companies, summarized by AI.</p>
        </div>
        <button type="button" onClick={handleRunIngestion} disabled={isRunningIngestion}>
          {isRunningIngestion ? "Fetching..." : "Fetch new signals"}
        </button>
      </div>

      {ingestionResult && (
        <div className="panel-card">
          <p className="subtitle">
            Checked {ingestionResult.target_companies_processed} target compan
            {ingestionResult.target_companies_processed === 1 ? "y" : "ies"}, found{" "}
            {ingestionResult.articles_new} new article(s), created {ingestionResult.signals_created}{" "}
            signal(s).
          </p>
          {ingestionResult.errors.length > 0 && (
            <ul className="error-list">
              {ingestionResult.errors.map((message) => (
                <li key={message} className="error-text">
                  {message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="panel-card">
        <div className="field-row">
          <label>
            Target company
            <select value={companyFilter} onChange={(e) => setCompanyFilter(e.target.value)}>
              <option value="">All companies</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Status
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as SignalStatus | "")}
            >
              {STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && <p className="error-text">{error}</p>}
        {isLoading && <p className="subtitle">Loading signals...</p>}
        {!isLoading && signals.length === 0 && (
          <p className="subtitle">
            No signals yet. Add target companies and click "Fetch new signals" to get started.
          </p>
        )}

        <ul className="signal-list">
          {signals.map((signal) => (
            <li key={signal.id}>
              <Link to={`/signals/${signal.id}`} className="signal-row">
                <div className="signal-row-main">
                  <span className={`status-badge status-${signal.status}`}>{signal.status}</span>
                  <div>
                    <strong>{signal.target_company_name}</strong>
                    <div className="signal-title">{signal.article_title}</div>
                    <div className="subtitle">{signal.summary}</div>
                  </div>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
