import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiError } from "../api/client";
import type { IngestionRunResult, Signal, SignalStatus, TargetCompany, WorkspaceSettings } from "../api/types";
import Skeleton from "../components/Skeleton";
import SetupChecklist from "../components/SetupChecklist";
import EmptyStateIllustration from "../components/icons/EmptyStateIllustration";
import { STATUS_TRANSITIONS } from "../constants/signalStatus";
import { useToast } from "../context/ToastContext";
import { usePageTitle } from "../hooks/usePageTitle";

const STATUS_OPTIONS: { value: SignalStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "new", label: "New" },
  { value: "reviewed", label: "Reviewed" },
  { value: "archived", label: "Archived" },
  { value: "dismissed", label: "Dismissed" },
];

type SortOrder = "newest" | "oldest" | "relevance";

export default function SignalsFeed() {
  usePageTitle("Signals");
  const { showToast } = useToast();
  const [signals, setSignals] = useState<Signal[]>([]);
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [companyFilter, setCompanyFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<SignalStatus | "">("");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortOrder, setSortOrder] = useState<SortOrder>("newest");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [loadError, setLoadError] = useState<string | null>(null);
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
      .then((result) => {
        setSignals(result);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Failed to load signals"))
      .finally(() => setIsLoading(false));
  }

  useEffect(() => {
    api.get<TargetCompany[]>("/target-companies").then(setCompanies).catch(() => undefined);
    api.get<WorkspaceSettings>("/settings").then(setSettings).catch(() => undefined);
  }, []);

  useEffect(loadSignals, [companyFilter, statusFilter]);

  useEffect(() => {
    setSelectedIds(new Set());
  }, [signals]);

  async function handleRunIngestion() {
    setIngestionResult(null);
    setIsRunningIngestion(true);
    try {
      const result = await api.post<IngestionRunResult>("/ingestion/run-now");
      setIngestionResult(result);
      loadSignals();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Ingestion run failed", "error");
    } finally {
      setIsRunningIngestion(false);
    }
  }

  async function transitionSignal(id: string, status: SignalStatus) {
    try {
      const updated = await api.patch<Signal>(`/signals/${id}`, { status });
      setSignals((prev) => prev.map((s) => (s.id === id ? updated : s)));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to update signal", "error");
    }
  }

  async function transitionSelected(status: SignalStatus) {
    const ids = [...selectedIds];
    try {
      const updates = await Promise.all(
        ids.map((id) => api.patch<Signal>(`/signals/${id}`, { status }))
      );
      setSignals((prev) =>
        prev.map((s) => updates.find((updated) => updated.id === s.id) ?? s)
      );
      setSelectedIds(new Set());
      showToast(`Updated ${ids.length} signal${ids.length === 1 ? "" : "s"}.`, "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Bulk update failed", "error");
    }
  }

  function toggleSelected(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleSelectAll() {
    setSelectedIds((prev) => (prev.size === visibleSignals.length ? new Set() : new Set(visibleSignals.map((s) => s.id))));
  }

  const visibleSignals = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const filtered = query
      ? signals.filter(
          (s) =>
            s.article_title.toLowerCase().includes(query) ||
            s.summary.toLowerCase().includes(query) ||
            s.target_company_name.toLowerCase().includes(query)
        )
      : signals;
    const sorted = [...filtered].sort((a, b) => {
      if (sortOrder === "relevance") {
        const diff = (b.relevance_score ?? 0) - (a.relevance_score ?? 0);
        if (diff !== 0) return diff;
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
      const diff = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      return sortOrder === "newest" ? -diff : diff;
    });
    return sorted;
  }, [signals, searchQuery, sortOrder]);

  const hasCompanyProfile = Boolean(settings?.offering_description.trim());
  const hasTargetCompany = companies.length > 0;
  const showChecklist = settings !== null && (!hasCompanyProfile || !hasTargetCompany || signals.length === 0);

  return (
    <div>
      <div className="panel-card feed-toolbar">
        <div>
          <h2>Signals feed</h2>
          <p className="subtitle">News signals for your target companies, summarized by AI.</p>
        </div>
        <button
          type="button"
          onClick={handleRunIngestion}
          disabled={isRunningIngestion || !hasTargetCompany}
          title={hasTargetCompany ? undefined : "Add a target company first"}
        >
          {isRunningIngestion && <span className="spinner" aria-hidden="true" />}
          {isRunningIngestion ? "Fetching..." : "Fetch new signals"}
        </button>
      </div>

      {showChecklist && (
        <SetupChecklist
          hasCompanyProfile={hasCompanyProfile}
          hasTargetCompany={hasTargetCompany}
          hasSignals={signals.length > 0}
        />
      )}

      {ingestionResult && (
        <div className="panel-card">
          <p className="subtitle">
            Checked {ingestionResult.target_companies_processed} target compan
            {ingestionResult.target_companies_processed === 1 ? "y" : "ies"}, found{" "}
            {ingestionResult.articles_new} new article(s), created {ingestionResult.signals_created}{" "}
            signal(s)
            {(ingestionResult.duplicates_skipped > 0 || ingestionResult.triaged_out > 0) && (
              <>
                {" "}({ingestionResult.duplicates_skipped} duplicate(s) and{" "}
                {ingestionResult.triaged_out} low-relevance article(s) skipped without a full
                AI call)
              </>
            )}
            .
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
        <div className="field-row">
          <label>
            Search
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search title, summary, or company..."
            />
          </label>
          <label>
            Sort
            <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value as SortOrder)}>
              <option value="newest">Newest first</option>
              <option value="oldest">Oldest first</option>
              <option value="relevance">Most relevant first</option>
            </select>
          </label>
        </div>

        {loadError && <p className="error-text">{loadError}</p>}
        {isLoading && <Skeleton rows={4} />}
        {!isLoading && !loadError && visibleSignals.length === 0 && signals.length === 0 && (
          <div className="empty-state">
            <EmptyStateIllustration />
            <p className="subtitle">
              No signals yet. Add target companies and click "Fetch new signals" to get started.
            </p>
          </div>
        )}
        {!isLoading && !loadError && visibleSignals.length === 0 && signals.length > 0 && (
          <p className="subtitle">No signals match your search.</p>
        )}

        {!isLoading && visibleSignals.length > 0 && (
          <>
            <div className="feed-select-all">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={selectedIds.size === visibleSignals.length}
                  onChange={toggleSelectAll}
                />
                Select all
              </label>
              {selectedIds.size > 0 && (
                <div className="bulk-actions">
                  <span className="subtitle">{selectedIds.size} selected</span>
                  {STATUS_TRANSITIONS.map((transition) => (
                    <button
                      type="button"
                      key={transition.value}
                      className="secondary"
                      onClick={() => transitionSelected(transition.value)}
                    >
                      {transition.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <ul className="signal-list">
              {visibleSignals.map((signal) => (
                <li key={signal.id}>
                  <div className="signal-row">
                    <input
                      type="checkbox"
                      className="signal-checkbox"
                      checked={selectedIds.has(signal.id)}
                      onChange={() => toggleSelected(signal.id)}
                      aria-label={`Select ${signal.article_title}`}
                    />
                    <Link to={`/signals/${signal.id}`} className="signal-row-link">
                      <div className="signal-row-main">
                        <span className={`status-badge status-${signal.status}`}>{signal.status}</span>
                        {signal.relevance_score !== null && (
                          <span className={`score-badge score-${signal.relevance_score}`}>
                            {signal.relevance_score}/5
                          </span>
                        )}
                        <div>
                          <strong>{signal.target_company_name}</strong>
                          <div className="signal-title">{signal.article_title}</div>
                          <div className="subtitle">{signal.summary}</div>
                        </div>
                      </div>
                    </Link>
                    <div className="signal-row-actions">
                      {STATUS_TRANSITIONS.filter((t) => t.value !== signal.status).map((transition) => (
                        <button
                          type="button"
                          key={transition.value}
                          className="secondary"
                          onClick={() => transitionSignal(signal.id, transition.value)}
                        >
                          {transition.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
