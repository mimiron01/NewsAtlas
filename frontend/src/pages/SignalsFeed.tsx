import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { ARTICLE_SOURCE_LABELS } from "../api/types";
import type { IngestionRunStatus, Signal, SignalStatus, TargetCompany, WorkspaceSettings } from "../api/types";
import Skeleton from "../components/Skeleton";
import SetupChecklist from "../components/SetupChecklist";
import SignalRow from "../components/SignalRow";
import EmptyStateIllustration from "../components/icons/EmptyStateIllustration";
import { STATUS_TRANSITIONS } from "../constants/signalStatus";
import { useToast } from "../context/ToastContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { usePageTitle } from "../hooks/usePageTitle";

const STATUS_OPTIONS: { value: SignalStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "new", label: "New" },
  { value: "reviewed", label: "Reviewed" },
  { value: "archived", label: "Archived" },
  { value: "dismissed", label: "Dismissed" },
];

type SortOrder = "newest" | "oldest" | "relevance";

const POLL_INTERVAL_MS = 1500;

function ingestionStatusText(status: IngestionRunStatus): string {
  if (status.status === "failed") {
    return status.fatal_error ? `Ingestion run failed: ${status.fatal_error}` : "Ingestion run failed.";
  }
  if (status.status === "completed") {
    return "Finishing up...";
  }
  const companyPosition = Math.min(status.companies_processed + 1, Math.max(status.companies_total, 1));
  const companyProgress =
    status.companies_total > 0 ? ` (company ${companyPosition} of ${status.companies_total})` : "";
  if (status.current_step === "summarizing" && status.articles_total_this_company > 0) {
    const articlePosition = Math.min(
      status.articles_processed_this_company + 1,
      status.articles_total_this_company
    );
    return `Summarizing articles for ${status.current_company_name ?? "target company"} — article ${articlePosition} of ${status.articles_total_this_company}${companyProgress}`;
  }
  if (status.current_company_name) {
    return `Fetching articles for ${status.current_company_name}${companyProgress}`;
  }
  return "Starting...";
}

export default function SignalsFeed() {
  usePageTitle("Signals");
  const { showToast } = useToast();
  const isAdmin = useIsAdmin();
  const [searchParams] = useSearchParams();
  const [signals, setSignals] = useState<Signal[]>([]);
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [companyFilter, setCompanyFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<SignalStatus | "">(
    (searchParams.get("status") as SignalStatus | null) ?? ""
  );
  const [favoritedOnly, setFavoritedOnly] = useState(searchParams.get("favorited") === "true");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortOrder, setSortOrder] = useState<SortOrder>("newest");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [ingestionStatus, setIngestionStatus] = useState<IngestionRunStatus | null>(null);
  // Tracks whether *this page load* actually watched a run go through "running" — so a
  // long-finished run from before the page was opened doesn't make it look like a fetch
  // just happened the moment you land here.
  const sawRunningRef = useRef(false);
  const isRunningIngestion = ingestionStatus?.status === "running";

  function loadSignals() {
    setIsLoading(true);
    const params = new URLSearchParams();
    if (companyFilter) params.set("company_id", companyFilter);
    if (statusFilter) params.set("status", statusFilter);
    if (favoritedOnly) params.set("favorited", "true");
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
    // /settings is admin-only; regular users can't view or fix the company profile anyway,
    // so skip the call rather than eat a 403 on every page load.
    if (isAdmin) {
      api.get<WorkspaceSettings>("/settings").then(setSettings).catch(() => undefined);
    }
  }, [isAdmin]);

  useEffect(loadSignals, [companyFilter, statusFilter, favoritedOnly]);

  async function pollIngestionStatus() {
    try {
      const result = await api.get<IngestionRunStatus | null>("/ingestion/status");
      if (result?.status === "running") {
        sawRunningRef.current = true;
      }
      setIngestionStatus(result);
      if (sawRunningRef.current && result && result.status !== "running") {
        loadSignals();
      }
    } catch {
      // Transient poll failure — the next tick (or the next page load) will pick it back up.
    }
  }

  // Resumes tracking a run already in flight (e.g. the page was reloaded mid-fetch, or a
  // scheduled run happens to be running) instead of only ever reacting to this browser's
  // own button click.
  useEffect(() => {
    pollIngestionStatus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!isRunningIngestion) return;
    const interval = window.setInterval(pollIngestionStatus, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRunningIngestion]);

  useEffect(() => {
    setSelectedIds(new Set());
  }, [signals]);

  async function handleFavoriteToggle(signal: Signal) {
    const nextFavorited = !signal.is_favorited;
    setSignals((prev) => prev.map((s) => (s.id === signal.id ? { ...s, is_favorited: nextFavorited } : s)));
    try {
      const updated = nextFavorited
        ? await api.post<Signal>(`/signals/${signal.id}/favorite`)
        : await api.delete<Signal>(`/signals/${signal.id}/favorite`);
      setSignals((prev) => prev.map((s) => (s.id === signal.id ? updated : s)));
    } catch (err) {
      setSignals((prev) =>
        prev.map((s) => (s.id === signal.id ? { ...s, is_favorited: signal.is_favorited } : s))
      );
      showToast(err instanceof ApiError ? err.message : "Failed to update favorite", "error");
    }
  }

  async function handleRunIngestion() {
    try {
      const result = await api.post<IngestionRunStatus>("/ingestion/run-now");
      sawRunningRef.current = true;
      setIngestionStatus(result);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to start ingestion run", "error");
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

  // Non-admins can't view or fix the company profile (admin-only), so treat it as
  // satisfied for them rather than gating the checklist on data they'll never fetch.
  const hasCompanyProfile = isAdmin ? Boolean(settings?.offering_description.trim()) : true;
  const hasTargetCompany = companies.length > 0;
  const settingsReady = !isAdmin || settings !== null;
  const showChecklist = settingsReady && (!hasCompanyProfile || !hasTargetCompany || signals.length === 0);

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
          {isRunningIngestion
            ? `Fetching... ${ingestionStatus?.progress_percent ?? 0}%`
            : "Fetch new signals"}
        </button>
      </div>

      {showChecklist && (
        <SetupChecklist
          hasCompanyProfile={hasCompanyProfile}
          hasTargetCompany={hasTargetCompany}
          hasSignals={signals.length > 0}
        />
      )}

      {isRunningIngestion && ingestionStatus && (
        <div className="panel-card">
          <div className="progress-bar">
            <div className="progress-bar-fill" style={{ width: `${ingestionStatus.progress_percent}%` }} />
          </div>
          <p className="field-hint">{ingestionStatusText(ingestionStatus)}</p>
        </div>
      )}

      {sawRunningRef.current && ingestionStatus && ingestionStatus.status === "failed" && (
        <div className="panel-card">
          <p className="error-text">{ingestionStatusText(ingestionStatus)}</p>
        </div>
      )}

      {sawRunningRef.current && ingestionStatus && ingestionStatus.status === "completed" && (
        <div className="panel-card">
          <p className="subtitle">
            Checked {ingestionStatus.companies_total} target compan
            {ingestionStatus.companies_total === 1 ? "y" : "ies"}, found{" "}
            {ingestionStatus.articles_new} new article(s), created {ingestionStatus.signals_created}{" "}
            signal(s)
            {(ingestionStatus.duplicates_skipped > 0 || ingestionStatus.triaged_out > 0) && (
              <>
                {" "}({ingestionStatus.duplicates_skipped} duplicate(s) and{" "}
                {ingestionStatus.triaged_out} low-relevance article(s) skipped without a full
                AI call)
              </>
            )}
            .
          </p>
          {Object.keys(ingestionStatus.by_source).length > 0 && (
            <p className="field-hint">
              By source:{" "}
              {Object.entries(ingestionStatus.by_source)
                .map(([source, count]) => `${ARTICLE_SOURCE_LABELS[source as keyof typeof ARTICLE_SOURCE_LABELS] ?? source}: ${count}`)
                .join(", ")}
            </p>
          )}
          {Object.keys(ingestionStatus.rate_limited).length > 0 && (
            <p className="field-hint error-text">
              Rate limited (skipped, no request made):{" "}
              {Object.entries(ingestionStatus.rate_limited)
                .map(([source, count]) => `${ARTICLE_SOURCE_LABELS[source as keyof typeof ARTICLE_SOURCE_LABELS] ?? source}: ${count} compan${count === 1 ? "y" : "ies"}`)
                .join(", ")}
            </p>
          )}
          {ingestionStatus.errors.length > 0 && (
            <ul className="error-list">
              {ingestionStatus.errors.map((message) => (
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
          <label className="checkbox-label favorites-filter">
            <input
              type="checkbox"
              checked={favoritedOnly}
              onChange={(e) => setFavoritedOnly(e.target.checked)}
            />
            Favorites only
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
        {!isLoading && !loadError && visibleSignals.length === 0 && signals.length === 0 && favoritedOnly && (
          <div className="empty-state">
            <EmptyStateIllustration />
            <p className="subtitle">
              You haven't favorited any signals yet. Star a signal to pin it here.
            </p>
          </div>
        )}
        {!isLoading && !loadError && visibleSignals.length === 0 && signals.length === 0 && !favoritedOnly && (
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
                <SignalRow
                  key={signal.id}
                  signal={signal}
                  onFavoriteToggle={handleFavoriteToggle}
                  selection={{
                    checked: selectedIds.has(signal.id),
                    onToggle: () => toggleSelected(signal.id),
                  }}
                  onTransition={transitionSignal}
                />
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
