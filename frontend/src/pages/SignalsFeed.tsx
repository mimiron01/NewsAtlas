import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import type {
  IngestionRunStatus,
  Signal,
  SignalStatus,
  TargetCompany,
  ThemeWatch,
  WorkspaceSettings,
} from "../api/types";
import Skeleton from "../components/Skeleton";
import SetupChecklist from "../components/SetupChecklist";
import SignalRow from "../components/SignalRow";
import IngestionStatusPanel from "../components/IngestionStatusPanel";
import EmptyStateIllustration from "../components/icons/EmptyStateIllustration";
import { STATUS_TRANSITION_VALUES } from "../constants/signalStatus";
import { useToast } from "../context/ToastContext";
import { useIngestionStatus } from "../hooks/useIngestionStatus";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { usePageTitle } from "../hooks/usePageTitle";

type SortOrder = "newest" | "oldest" | "relevance";

// Archived/dismissed signals live on the dedicated Archive page (see
// docs/archive-dismiss-ux-planning.html) instead of cluttering this default working list,
// so the filter here only ever offers the active statuses.
const SIGNAL_STATUSES: SignalStatus[] = ["new", "reviewed"];

export default function SignalsFeed() {
  const { t } = useTranslation("signals");
  usePageTitle(t("feed.title"));
  const { showToast } = useToast();
  const isAdmin = useIsAdmin();
  const [searchParams] = useSearchParams();
  const [signals, setSignals] = useState<Signal[]>([]);
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [themes, setThemes] = useState<ThemeWatch[]>([]);
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
    api.get<ThemeWatch[]>("/theme-watches").then(setThemes).catch(() => undefined);
    // /settings is admin-only; regular users can't view or fix the company profile anyway,
    // so skip the call rather than eat a 403 on every page load.
    if (isAdmin) {
      api.get<WorkspaceSettings>("/settings").then(setSettings).catch(() => undefined);
    }
  }, [isAdmin]);

  useEffect(loadSignals, [companyFilter, statusFilter, favoritedOnly]);

  // Resumes tracking a run already in flight (e.g. the page was reloaded mid-fetch, or a
  // scheduled run happens to be running) instead of only ever reacting to this browser's
  // own button click, and refreshes the signal list once a run this page watched settles.
  const { ingestionStatus, setIngestionStatus, isRunning: isRunningIngestion } =
    useIngestionStatus(loadSignals);

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
      if (status === "archived" && previousStatus) {
        showToast(t("archivedToast"), "success", {
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
    // Captured before the mutation so an undo can restore each signal's own prior
    // status, not one shared value — a bulk selection can span multiple statuses.
    const previousById = new Map(ids.map((id) => [id, signals.find((s) => s.id === id)?.status]));
    try {
      const updates = await Promise.all(
        ids.map((id) => api.patch<Signal>(`/signals/${id}`, { status }))
      );
      setSignals((prev) =>
        prev.map((s) => updates.find((updated) => updated.id === s.id) ?? s)
      );
      setSelectedIds(new Set());
      if (status === "archived") {
        showToast(t("feed.bulkUpdated", { count: ids.length }), "success", {
          label: t("undo"),
          onClick: async () => {
            const reverted = await Promise.all(
              ids.map((id) => {
                const previous = previousById.get(id);
                return previous ? api.patch<Signal>(`/signals/${id}`, { status: previous }) : null;
              })
            );
            setSignals((prev) =>
              prev.map((s) => reverted.find((updated) => updated?.id === s.id) ?? s)
            );
          },
        });
      } else {
        showToast(t("feed.bulkUpdated", { count: ids.length }), "success");
      }
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
  // A run covers companies *and* topics, so either alone is enough to fetch. Gating on
  // companies left a topics-only user unable to start a run at all.
  const hasSomethingToFetch = hasTargetCompany || themes.length > 0;
  const settingsReady = !isAdmin || settings !== null;
  const showChecklist =
    settingsReady && (!hasCompanyProfile || !hasSomethingToFetch || signals.length === 0);

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
          disabled={isRunningIngestion || !hasSomethingToFetch}
          title={hasSomethingToFetch ? undefined : t("feed.addCompanyOrThemeFirst")}
        >
          {isRunningIngestion
            ? t("feed.fetching", { percent: ingestionStatus?.progress_percent ?? 0 })
            : t("feed.fetchNewSignals")}
        </button>
      </div>

      {showChecklist && (
        <SetupChecklist
          hasCompanyProfile={hasCompanyProfile}
          hasTargetCompany={hasSomethingToFetch}
          hasSignals={signals.length > 0}
        />
      )}

      <IngestionStatusPanel status={ingestionStatus} isAdmin={isAdmin} onCancel={handleCancelIngestion} />

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
                      title={t(`transitionHints.${status}`, { defaultValue: "" })}
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
