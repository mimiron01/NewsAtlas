import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import { ARTICLE_SOURCE_LABELS } from "../api/types";
import type { IngestionRunStatus, Signal, SignalStatus, TargetCompany, WorkspaceSettings } from "../api/types";
import Skeleton from "../components/Skeleton";
import SetupChecklist from "../components/SetupChecklist";
import SignalRow from "../components/SignalRow";
import EmptyStateIllustration from "../components/icons/EmptyStateIllustration";
import { STATUS_TRANSITION_VALUES } from "../constants/signalStatus";
import { useToast } from "../context/ToastContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { usePageTitle } from "../hooks/usePageTitle";

type SortOrder = "newest" | "oldest" | "relevance";

const POLL_INTERVAL_MS = 1500;
const SIGNAL_STATUSES: SignalStatus[] = ["new", "reviewed", "archived", "dismissed"];

export default function SignalsFeed() {
  const { t } = useTranslation("signals");
  usePageTitle(t("feed.title"));
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
  // A high fraction of triaged-out articles isn't necessarily a bug, but an admin should
  // be able to notice and investigate rather than only ever seeing an aggregate count —
  // computed from the non-duplicate new articles (the ones that actually reached the
  // triage gate), not the raw fetch count, so a run dominated by duplicates doesn't also
  // read as a relevance problem.
  const nonDuplicateNewCount = ingestionStatus
    ? ingestionStatus.articles_new - ingestionStatus.duplicates_skipped
    : 0;
  const triageSkipRate =
    ingestionStatus && nonDuplicateNewCount > 0 ? ingestionStatus.triaged_out / nonDuplicateNewCount : 0;
  const showHighSkipRateWarning =
    isAdmin &&
    ingestionStatus?.status === "completed" &&
    nonDuplicateNewCount >= 3 &&
    triageSkipRate >= 0.7;

  function ingestionStatusText(status: IngestionRunStatus): string {
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
        company: status.current_company_name ?? t("feed.ingestion.defaultCompanyName"),
        companyProgress,
      });
    }
    if (status.current_company_name) {
      return t("feed.ingestion.fetching", { company: status.current_company_name, companyProgress });
    }
    return t("feed.ingestion.starting");
  }

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
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("feed.loadFailed")))
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
      showToast(err instanceof ApiError ? err.message : t("feed.favoriteUpdateFailed"), "error");
    }
  }

  async function handleRunIngestion() {
    try {
      const result = await api.post<IngestionRunStatus>("/ingestion/run-now");
      sawRunningRef.current = true;
      setIngestionStatus(result);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("feed.ingestionStartFailed"), "error");
    }
  }

  async function handleCancelIngestion() {
    if (!ingestionStatus) return;
    try {
      const result = await api.post<IngestionRunStatus>(`/ingestion/runs/${ingestionStatus.id}/cancel`);
      setIngestionStatus(result);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("feed.ingestion.stopFailed"), "error");
    }
  }

  async function transitionSignal(id: string, status: SignalStatus) {
    const previousStatus = signals.find((s) => s.id === id)?.status;
    try {
      const updated = await api.patch<Signal>(`/signals/${id}`, { status });
      setSignals((prev) => prev.map((s) => (s.id === id ? updated : s)));
      if (status === "dismissed" && previousStatus) {
        showToast(t("dismissedToast"), "success", {
          label: t("undo"),
          onClick: () => transitionSignal(id, previousStatus),
        });
      }
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("feed.signalUpdateFailed"), "error");
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
      showToast(t("feed.bulkUpdated", { count: ids.length }), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("feed.bulkUpdateFailed"), "error");
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
          <h2>{t("feed.title")}</h2>
          <p className="subtitle">{t("feed.subtitle")}</p>
        </div>
        <button
          type="button"
          onClick={handleRunIngestion}
          disabled={isRunningIngestion || !hasTargetCompany}
          title={hasTargetCompany ? undefined : t("feed.addTargetCompanyFirst")}
        >
          {isRunningIngestion
            ? t("feed.fetching", { percent: ingestionStatus?.progress_percent ?? 0 })
            : t("feed.fetchNewSignals")}
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
          <div className="ingestion-progress-row">
            <p className="field-hint">{ingestionStatusText(ingestionStatus)}</p>
            {isAdmin && (
              <button
                type="button"
                className="danger"
                onClick={handleCancelIngestion}
                disabled={ingestionStatus.cancel_requested}
              >
                {ingestionStatus.cancel_requested ? t("feed.ingestion.stopping") : t("feed.ingestion.stop")}
              </button>
            )}
          </div>
        </div>
      )}

      {sawRunningRef.current && ingestionStatus && ingestionStatus.status === "failed" && (
        <div className="panel-card">
          <p className="error-text">{ingestionStatusText(ingestionStatus)}</p>
        </div>
      )}

      {sawRunningRef.current && ingestionStatus && ingestionStatus.status === "cancelled" && (
        <div className="panel-card">
          <p className="subtitle">
            {t("feed.ingestion.cancelledProgress", {
              processed: ingestionStatus.companies_processed,
              total: ingestionStatus.companies_total,
            })}
            {t("feed.ingestion.articlesFound", { count: ingestionStatus.articles_new })}
            {t("feed.ingestion.signalsCreatedText", { count: ingestionStatus.signals_created })}.
          </p>
        </div>
      )}

      {sawRunningRef.current && ingestionStatus && ingestionStatus.status === "completed" && (
        <div className="panel-card">
          <p className="subtitle">
            {t("feed.ingestion.companiesChecked", { count: ingestionStatus.companies_total })}
            {t("feed.ingestion.articlesFound", { count: ingestionStatus.articles_new })}
            {t("feed.ingestion.signalsCreatedText", { count: ingestionStatus.signals_created })}
            {(ingestionStatus.duplicates_skipped > 0 || ingestionStatus.triaged_out > 0) && (
              <>
                {" "}
                {t("feed.ingestion.skippedSuffix", {
                  duplicates: t("feed.ingestion.duplicatesSkipped", {
                    count: ingestionStatus.duplicates_skipped,
                  }),
                  lowRelevance: t("feed.ingestion.lowRelevanceSkipped", {
                    count: ingestionStatus.triaged_out,
                  }),
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
          {Object.keys(ingestionStatus.by_source).length > 0 && (
            <p className="field-hint">
              {t("feed.bySource")}{" "}
              {Object.entries(ingestionStatus.by_source)
                .map(([source, count]) => `${ARTICLE_SOURCE_LABELS[source as keyof typeof ARTICLE_SOURCE_LABELS] ?? source}: ${count}`)
                .join(", ")}
            </p>
          )}
          {Object.keys(ingestionStatus.rate_limited).length > 0 && (
            <p className="field-hint error-text">
              {t("feed.rateLimited")}{" "}
              {Object.entries(ingestionStatus.rate_limited)
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
            {t("feed.targetCompany")}
            <select value={companyFilter} onChange={(e) => setCompanyFilter(e.target.value)}>
              <option value="">{t("feed.allCompanies")}</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("feed.statusLabel")}
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as SignalStatus | "")}
            >
              <option value="">{t("status.all")}</option>
              {SIGNAL_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {t(`status.${status}`)}
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
            {t("feed.favoritesOnly")}
          </label>
        </div>
        <div className="field-row">
          <label>
            {t("feed.search")}
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t("feed.searchPlaceholder")}
            />
          </label>
          <label>
            {t("feed.sort")}
            <select value={sortOrder} onChange={(e) => setSortOrder(e.target.value as SortOrder)}>
              <option value="newest">{t("feed.sortNewest")}</option>
              <option value="oldest">{t("feed.sortOldest")}</option>
              <option value="relevance">{t("feed.sortRelevance")}</option>
            </select>
          </label>
        </div>

        {loadError && <p className="error-text">{loadError}</p>}
        {isLoading && <Skeleton rows={4} />}
        {!isLoading && !loadError && visibleSignals.length === 0 && signals.length === 0 && favoritedOnly && (
          <div className="empty-state">
            <EmptyStateIllustration />
            <p className="subtitle">{t("feed.noFavoritesYet")}</p>
          </div>
        )}
        {!isLoading && !loadError && visibleSignals.length === 0 && signals.length === 0 && !favoritedOnly && (
          <div className="empty-state">
            <EmptyStateIllustration />
            <p className="subtitle">{t("feed.noSignalsYet")}</p>
          </div>
        )}
        {!isLoading && !loadError && visibleSignals.length === 0 && signals.length > 0 && (
          <p className="subtitle">{t("feed.noSearchMatches")}</p>
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
                {t("feed.selectAll")}
              </label>
              {selectedIds.size > 0 && (
                <div className="bulk-actions">
                  <span className="subtitle">{t("feed.selectedCount", { count: selectedIds.size })}</span>
                  {STATUS_TRANSITION_VALUES.map((status) => (
                    <button
                      type="button"
                      key={status}
                      className="secondary"
                      onClick={() => transitionSelected(status)}
                    >
                      {t(`transitions.${status}`)}
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
