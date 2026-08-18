import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import type {
  BackfillTriggerResult,
  IngestionRunStatus,
  PublicWorkspaceSettings,
  Signal,
  SignalStatus,
  TargetCompany,
  TargetCompanyBulkDeleteResult,
  ThemeWatch,
  WorkspaceSettings,
} from "../api/types";
import EmptyStateIllustration from "../components/icons/EmptyStateIllustration";
import IngestionStatusPanel from "../components/IngestionStatusPanel";
import Modal from "../components/Modal";
import OverflowMenu from "../components/OverflowMenu";
import SetupChecklist from "../components/SetupChecklist";
import SignalRow from "../components/SignalRow";
import Skeleton from "../components/Skeleton";
import SourceAllowlistField from "../components/SourceAllowlistField";
import TagInput from "../components/TagInput";
import TargetCompanyCsvImport from "../components/TargetCompanyCsvImport";
import { STATUS_TRANSITION_VALUES } from "../constants/signalStatus";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { useIngestionStatus } from "../hooks/useIngestionStatus";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { useLocaleFormat } from "../hooks/useLocaleFormat";
import { usePageTitle } from "../hooks/usePageTitle";

// Verfolgte Unternehmen only ever shows this many rows by default (see
// TRACKED_COMPANIES_COLLAPSED_LIMIT below) — a table that already has its own
// search/sort doesn't need every row visible at once, and collapsing keeps a workspace
// with dozens of companies from pushing the merged-in Signale section far down the page.
const TRACKED_COMPANIES_COLLAPSED_LIMIT = 5;

// Archived/dismissed signals live on the dedicated Archive page (see
// docs/archive-dismiss-ux-planning.html) instead of cluttering this default working list,
// so the filter here only ever offers the active statuses.
const SIGNAL_STATUSES: SignalStatus[] = ["new", "reviewed"];
type SignalSortOrder = "newest" | "oldest" | "relevance";

export default function SettingsTargets() {
  const { t } = useTranslation(["settings", "signals"]);
  usePageTitle(t("targets.title"));
  const { showToast } = useToast();
  const { user } = useAuth();
  const isAdmin = useIsAdmin();
  const { formatDate } = useLocaleFormat();
  const [searchParams] = useSearchParams();
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [name, setName] = useState("");
  const [aliases, setAliases] = useState<string[]>([]);
  const [contextTerms, setContextTerms] = useState<string[]>([]);
  const [excludeTerms, setExclusionTerms] = useState<string[]>([]);
  const [industry, setIndustry] = useState("");
  // null = inherit the workspace allowlist. Kept as null rather than [] so a new company
  // defaults to inheriting, which is what almost every company should do.
  const [sourceAllowlist, setSourceAllowlist] = useState<string[] | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [justCreatedId, setJustCreatedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmingBulk, setConfirmingBulk] = useState(false);
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);
  const [isBulkRunning, setIsBulkRunning] = useState(false);
  // Resumes tracking a run already in flight (page reloaded mid-fetch, a scheduled run
  // happens to be going, or another user started one) rather than only reacting to this
  // browser's own click — same pattern as the Themes page. One shared instance for the
  // whole merged page (companies + Signale), refreshing both lists once a watched run
  // settles rather than the two separate instances each section had as standalone pages.
  const { ingestionStatus, setIngestionStatus, isRunning: isRunningIngestion } = useIngestionStatus(() => {
    loadCompanies();
    loadSignals();
  });
  const [editName, setEditName] = useState("");
  const [editAliases, setEditAliases] = useState<string[]>([]);
  const [editContextTerms, setEditContextTerms] = useState<string[]>([]);
  const [editExclusionTerms, setEditExclusionTerms] = useState<string[]>([]);
  const [editIndustry, setEditIndustry] = useState("");
  const [editSourceAllowlist, setEditSourceAllowlist] = useState<string[] | null>(null);
  // List-level search/sort (parity with ThemesPage's toolbar) — client-side, same
  // reasoning as there: the list is small and there's no server-side paging for it.
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<"name" | "created">("name");
  // Verfolgte Unternehmen shows at most TRACKED_COMPANIES_COLLAPSED_LIMIT rows until the
  // user opts into seeing the rest.
  const [companiesExpanded, setCompaniesExpanded] = useState(false);

  // --- Signale: this page absorbed the former standalone /signals route (see item 8 of
  // the Themen-page-fixes request) — its state/handlers below are otherwise unchanged
  // from that page, just relocated and prefixed with "signal" where a name would
  // otherwise collide with the company-table state above. ---
  const [themes, setThemes] = useState<ThemeWatch[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [signalCompanyFilter, setSignalCompanyFilter] = useState("");
  const [signalStatusFilter, setSignalStatusFilter] = useState<SignalStatus | "">(
    (searchParams.get("status") as SignalStatus | null) ?? ""
  );
  const [signalFavoritedOnly, setSignalFavoritedOnly] = useState(searchParams.get("favorited") === "true");
  const [signalSearchQuery, setSignalSearchQuery] = useState("");
  const [signalSortOrder, setSignalSortOrder] = useState<SignalSortOrder>("newest");
  const [selectedSignalIds, setSelectedSignalIds] = useState<Set<string>>(new Set());
  const [signalsLoadError, setSignalsLoadError] = useState<string | null>(null);
  const [isSignalsLoading, setIsSignalsLoading] = useState(true);

  function canEdit(company: TargetCompany): boolean {
    return isAdmin || (user !== null && company.created_by === user.id);
  }
  const [publicSettings, setPublicSettings] = useState<PublicWorkspaceSettings | null>(null);
  // Full workspace settings, admin-only (a regular user can't view or fix the company
  // profile anyway, so skip the call rather than eat a 403 on every page load). Backs
  // both the backfill-availability check below and the Signale checklist's
  // hasCompanyProfile check.
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const backfillEnabled = Boolean(settings?.newsdata_enabled && settings.newsdata_backfill_days > 0);

  function loadCompanies() {
    api
      .get<TargetCompany[]>("/target-companies")
      .then(setCompanies)
      .catch((err) => showToast(err instanceof ApiError ? err.message : t("targets.loadFailed"), "error"));
  }

  function loadSignals() {
    setIsSignalsLoading(true);
    const params = new URLSearchParams();
    if (signalCompanyFilter) params.set("company_id", signalCompanyFilter);
    if (signalStatusFilter) params.set("status", signalStatusFilter);
    if (signalFavoritedOnly) params.set("favorited", "true");
    const query = params.toString();
    api
      .get<Signal[]>(`/signals${query ? `?${query}` : ""}`)
      .then((result) => {
        setSignals(result);
        setSignalsLoadError(null);
      })
      .catch((err) =>
        setSignalsLoadError(err instanceof ApiError ? err.message : t("feed.loadFailed", { ns: "signals" }))
      )
      .finally(() => setIsSignalsLoading(false));
  }

  useEffect(loadCompanies, [t]);
  useEffect(loadSignals, [signalCompanyFilter, signalStatusFilter, signalFavoritedOnly]);

  useEffect(() => {
    const validIds = new Set(companies.map((c) => c.id));
    setSelectedIds((prev) => {
      const next = new Set(Array.from(prev).filter((id) => validIds.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [companies]);

  useEffect(() => {
    setSelectedSignalIds(new Set());
  }, [signals]);

  useEffect(() => {
    if (!isAdmin) return;
    api.get<WorkspaceSettings>("/settings").then(setSettings).catch(() => undefined);
  }, [isAdmin]);

  useEffect(() => {
    // Readable by every user (unlike /settings above), so every user — not just admins —
    // learns whether a fetch can produce anything at all right now.
    api.get<PublicWorkspaceSettings>("/settings/public").then(setPublicSettings).catch(() => undefined);
    // Topics count as fetchable work too (see hasSomethingToFetch below) — a user
    // tracking only topics must still be able to start a run from this page's Signale
    // section.
    api.get<ThemeWatch[]>("/theme-watches").then(setThemes).catch(() => undefined);
  }, []);

  // Treated as available until the flags load, so the UI doesn't flash a warning it may
  // immediately retract (same reasoning as ThemesPage's googleNewsDisabled).
  const noSourceEnabled = publicSettings !== null && !publicSettings.any_news_source_enabled;

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const created = await api.post<TargetCompany>("/target-companies", {
        name,
        aliases,
        context_terms: contextTerms,
        exclude_terms: excludeTerms,
        industry: industry || null,
        google_news_source_allowlist: sourceAllowlist,
      });
      setName("");
      setAliases([]);
      setContextTerms([]);
      setExclusionTerms([]);
      setIndustry("");
      setSourceAllowlist(null);
      setIsAddModalOpen(false);
      showToast(t("targets.addedToast"), "success");
      if (backfillEnabled && created.backfilled_at === null) {
        setJustCreatedId(created.id);
      }
      loadCompanies();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("targets.addFailed"), "error");
    } finally {
      setIsSubmitting(false);
    }
  }

  function startEdit(company: TargetCompany) {
    setConfirmingId(null);
    setEditingId(company.id);
    setEditName(company.name);
    setEditAliases(company.aliases);
    setEditContextTerms(company.context_terms);
    setEditExclusionTerms(company.exclude_terms);
    setEditIndustry(company.industry ?? "");
    setEditSourceAllowlist(company.google_news_source_allowlist);
  }

  function cancelEdit() {
    setEditingId(null);
  }

  async function saveEdit(event: FormEvent, company: TargetCompany) {
    event.preventDefault();
    setPendingId(company.id);
    try {
      await api.patch(`/target-companies/${company.id}`, {
        name: editName,
        aliases: editAliases,
        context_terms: editContextTerms,
        exclude_terms: editExclusionTerms,
        industry: editIndustry || null,
        // Sent explicitly, including as null: null means "go back to inheriting the
        // workspace list", which is a real edit, not an omission.
        google_news_source_allowlist: editSourceAllowlist,
      });
      setEditingId(null);
      showToast(t("targets.updatedToast", { name: editName }), "success");
      loadCompanies();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("targets.updateFailed"), "error");
    } finally {
      setPendingId(null);
    }
  }

  async function toggleActive(company: TargetCompany) {
    setPendingId(company.id);
    try {
      await api.patch(`/target-companies/${company.id}`, { is_active: !company.is_active });
      loadCompanies();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("targets.updateFailed"), "error");
    } finally {
      setPendingId(null);
    }
  }

  async function toggleMute(company: TargetCompany) {
    setPendingId(company.id);
    try {
      await api.post(`/target-companies/${company.id}/mute`);
      loadCompanies();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("targets.updateFailed"), "error");
    } finally {
      setPendingId(null);
    }
  }

  async function remove(company: TargetCompany) {
    setPendingId(company.id);
    try {
      await api.delete(`/target-companies/${company.id}`);
      showToast(
        isAdmin
          ? t("targets.deletedToast", { name: company.name })
          : t("targets.unfollowedToast", { name: company.name }),
        "success"
      );
      loadCompanies();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("targets.removeFailed"), "error");
    } finally {
      setPendingId(null);
      setConfirmingId(null);
    }
  }

  function toggleSelect(companyId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(companyId)) {
        next.delete(companyId);
      } else {
        next.add(companyId);
      }
      return next;
    });
  }

  function toggleSelectAll() {
    // Scoped to the currently displayed (collapsed-or-expanded) rows, not every row
    // matching the search — selecting something not currently visible would be confusing.
    setSelectedIds((prev) =>
      prev.size === displayedCompanies.length ? new Set() : new Set(displayedCompanies.map((c) => c.id))
    );
  }

  async function handleBulkDelete() {
    const ids = Array.from(selectedIds);
    setIsBulkDeleting(true);
    try {
      const result = await api.post<TargetCompanyBulkDeleteResult>("/target-companies/bulk-delete", {
        target_company_ids: ids,
      });
      showToast(
        isAdmin
          ? t("targets.bulkDeletedToast", { count: result.deleted })
          : t("targets.bulkUnfollowedToast", { count: result.deleted }),
        "success"
      );
      setSelectedIds(new Set());
      loadCompanies();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("targets.bulkRemoveFailed"), "error");
    } finally {
      setIsBulkDeleting(false);
      setConfirmingBulk(false);
    }
  }

  async function runCompanyNow(company: TargetCompany) {
    setPendingId(company.id);
    try {
      const result = await api.post<IngestionRunStatus>(`/target-companies/${company.id}/run-now`);
      setIngestionStatus(result);
      showToast(t("targets.runNowStartedToast", { name: company.name }), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("targets.runNowFailed"), "error");
    } finally {
      setPendingId(null);
    }
  }

  async function handleBulkRunNow() {
    const ids = Array.from(selectedIds);
    setIsBulkRunning(true);
    try {
      const result = await api.post<IngestionRunStatus>("/target-companies/run-now", {
        target_company_ids: ids,
      });
      setIngestionStatus(result);
      showToast(t("targets.bulkRunNowStartedToast", { count: result.companies_total }), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("targets.bulkRunNowFailed"), "error");
    } finally {
      setIsBulkRunning(false);
    }
  }

  async function handleCancelIngestion() {
    if (!ingestionStatus) return;
    try {
      const result = await api.post<IngestionRunStatus>(`/ingestion/runs/${ingestionStatus.id}/cancel`);
      setIngestionStatus(result);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("targets.cancelFetchFailed"), "error");
    }
  }

  async function triggerBackfill(company: TargetCompany) {
    setPendingId(company.id);
    try {
      const result = await api.post<BackfillTriggerResult>(`/target-companies/${company.id}/backfill`);
      showToast(result.message, "success");
      setJustCreatedId(company.id);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("targets.backfillFailed"), "error");
    } finally {
      setPendingId(null);
    }
  }

  function removeLabel(): string {
    return isAdmin ? t("targets.delete") : t("targets.unfollow");
  }

  function confirmCopy(company: TargetCompany): string {
    if (isAdmin) {
      return t("targets.confirmDeleteAdmin", { name: company.name });
    }
    if (company.follower_count <= 1) {
      return t("targets.confirmUnfollowOnly", { name: company.name });
    }
    return t("targets.confirmUnfollowShared", { name: company.name });
  }

  const visibleCompanies = companies
    .filter((company) => {
      const q = searchQuery.trim().toLowerCase();
      if (!q) return true;
      return (
        company.name.toLowerCase().includes(q) ||
        (company.industry ?? "").toLowerCase().includes(q) ||
        company.keywords.some((keyword) => keyword.toLowerCase().includes(q))
      );
    })
    .sort((a, b) => {
      if (sortBy === "name") return a.name.localeCompare(b.name);
      // "created": newest tracked first, by the current user's own follow date.
      return (b.followed_at ?? "").localeCompare(a.followed_at ?? "");
    });
  const displayedCompanies = companiesExpanded
    ? visibleCompanies
    : visibleCompanies.slice(0, TRACKED_COMPANIES_COLLAPSED_LIMIT);

  // --- Signale handlers (relocated from the former standalone /signals page) ---

  async function handleRunIngestion() {
    try {
      const result = await api.post<IngestionRunStatus>("/ingestion/run-now");
      setIngestionStatus(result);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("feed.ingestionStartFailed", { ns: "signals" }), "error");
    }
  }

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
      showToast(err instanceof ApiError ? err.message : t("feed.favoriteUpdateFailed", { ns: "signals" }), "error");
    }
  }

  async function transitionSignal(id: string, status: SignalStatus) {
    const previousStatus = signals.find((s) => s.id === id)?.status;
    try {
      const updated = await api.patch<Signal>(`/signals/${id}`, { status });
      setSignals((prev) => prev.map((s) => (s.id === id ? updated : s)));
      if (status === "archived" && previousStatus) {
        showToast(t("archivedToast", { ns: "signals" }), "success", {
          label: t("undo", { ns: "signals" }),
          onClick: () => transitionSignal(id, previousStatus),
        });
      }
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("feed.signalUpdateFailed", { ns: "signals" }), "error");
    }
  }

  async function transitionSelectedSignals(status: SignalStatus) {
    const ids = [...selectedSignalIds];
    // Captured before the mutation so an undo can restore each signal's own prior
    // status, not one shared value — a bulk selection can span multiple statuses.
    const previousById = new Map(ids.map((id) => [id, signals.find((s) => s.id === id)?.status]));
    try {
      const updates = await Promise.all(ids.map((id) => api.patch<Signal>(`/signals/${id}`, { status })));
      setSignals((prev) => prev.map((s) => updates.find((updated) => updated.id === s.id) ?? s));
      setSelectedSignalIds(new Set());
      if (status === "archived") {
        showToast(t("feed.bulkUpdated", { ns: "signals", count: ids.length }), "success", {
          label: t("undo", { ns: "signals" }),
          onClick: async () => {
            const reverted = await Promise.all(
              ids.map((id) => {
                const previous = previousById.get(id);
                return previous ? api.patch<Signal>(`/signals/${id}`, { status: previous }) : null;
              })
            );
            setSignals((prev) => prev.map((s) => reverted.find((updated) => updated?.id === s.id) ?? s));
          },
        });
      } else {
        showToast(t("feed.bulkUpdated", { ns: "signals", count: ids.length }), "success");
      }
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("feed.bulkUpdateFailed", { ns: "signals" }), "error");
    }
  }

  function toggleSignalSelected(id: string) {
    setSelectedSignalIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleSignalSelectAll() {
    setSelectedSignalIds((prev) =>
      prev.size === visibleSignals.length ? new Set() : new Set(visibleSignals.map((s) => s.id))
    );
  }

  const visibleSignals = useMemo(() => {
    const query = signalSearchQuery.trim().toLowerCase();
    const filtered = query
      ? signals.filter(
          (s) =>
            s.article_title.toLowerCase().includes(query) ||
            s.summary.toLowerCase().includes(query) ||
            s.target_company_name.toLowerCase().includes(query)
        )
      : signals;
    const sorted = [...filtered].sort((a, b) => {
      if (signalSortOrder === "relevance") {
        const diff = (b.relevance_score ?? 0) - (a.relevance_score ?? 0);
        if (diff !== 0) return diff;
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      }
      const diff = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      return signalSortOrder === "newest" ? -diff : diff;
    });
    return sorted;
  }, [signals, signalSearchQuery, signalSortOrder]);

  // Non-admins can't view or fix the company profile (admin-only), so treat it as
  // satisfied for them rather than gating the checklist on data they'll never fetch.
  const hasCompanyProfile = isAdmin ? Boolean(settings?.offering_description.trim()) : true;
  const hasTargetCompany = companies.length > 0;
  // A run covers companies *and* topics, so either alone is enough to fetch. Gating on
  // companies left a topics-only user unable to start a run at all.
  const hasSomethingToFetch = hasTargetCompany || themes.length > 0;
  const settingsReady = !isAdmin || settings !== null;
  const showSignalsChecklist =
    settingsReady && (!hasCompanyProfile || !hasSomethingToFetch || signals.length === 0);

  return (
    <div>
      <div className="panel-card">
        <div className="feed-toolbar">
          <div>
            <h2>{t("targets.title")}</h2>
            <p className="subtitle">{t("targets.subtitle")}</p>
          </div>
          <button type="button" onClick={() => setIsAddModalOpen(true)}>
            {t("targets.addButton")}
          </button>
        </div>
      </div>

      {noSourceEnabled && (
        <div className="panel-card warning-banner">
          <strong>{t("noNewsSource.title", { ns: "common" })}</strong>
          <p className="subtitle">
            {isAdmin
              ? t("noNewsSource.bodyAdmin", { ns: "common" })
              : t("noNewsSource.bodyMember", { ns: "common" })}
          </p>
          {isAdmin && (
            <Link to="/settings/sources" className="link-button">
              {t("noNewsSource.link", { ns: "common" })} →
            </Link>
          )}
        </div>
      )}

      <IngestionStatusPanel status={ingestionStatus} isAdmin={isAdmin} onCancel={handleCancelIngestion} />

      {isAddModalOpen && (
        <Modal title={t("targets.addButton")} onClose={() => setIsAddModalOpen(false)}>
          <form onSubmit={handleAdd}>
            <div className="field-row">
              <label>
                {t("targets.companyName")}
                <input value={name} onChange={(e) => setName(e.target.value)} required />
              </label>
              <label>
                {t("targets.industryOptional")}
                <input value={industry} onChange={(e) => setIndustry(e.target.value)} />
              </label>
            </div>
            <label>
              {t("targets.aliases")}
              <TagInput tags={aliases} onChange={setAliases} placeholder={t("targets.aliasesPlaceholder")} />
              <span className="field-hint">{t("targets.aliasesHint")}</span>
            </label>
            <label>
              {t("targets.contextTerms")}
              <TagInput
                tags={contextTerms}
                onChange={setContextTerms}
                placeholder={t("targets.contextTermsPlaceholder")}
              />
              <span className="field-hint">{t("targets.contextTermsHint")}</span>
            </label>
            <label>
              {t("targets.excludeTerms")}
              <TagInput
                tags={excludeTerms}
                onChange={setExclusionTerms}
                placeholder={t("targets.excludeTermsPlaceholder")}
              />
              <span className="field-hint">{t("targets.excludeTermsHint")}</span>
            </label>
            <SourceAllowlistField value={sourceAllowlist} onChange={setSourceAllowlist} />
            <button type="submit" disabled={isSubmitting}>
              {t("targets.addTargetCompany")}
            </button>
          </form>
        </Modal>
      )}

      <div className="panel-card">
        <div className="feed-toolbar">
          <h3>{t("targets.trackedCompanies", { count: companies.length })}</h3>
          <div className="toolbar-actions">
            {selectedIds.size > 0 && (
              <div className="bulk-actions">
                <span className="subtitle">{t("targets.selectedCount", { count: selectedIds.size })}</span>
                <button
                  type="button"
                  disabled={isBulkRunning || isRunningIngestion || noSourceEnabled}
                  title={
                    noSourceEnabled
                      ? t("noNewsSource.blockedTooltip", { ns: "common" })
                      : isRunningIngestion
                        ? t("targets.runNowBlockedRunning")
                        : undefined
                  }
                  onClick={handleBulkRunNow}
                >
                  {t("targets.bulkRunNow", { count: selectedIds.size })}
                </button>
                {confirmingBulk ? (
                  <>
                    <button type="button" className="danger" disabled={isBulkDeleting} onClick={handleBulkDelete}>
                      {t("targets.confirmAction", { action: removeLabel().toLowerCase() })}
                    </button>
                    <button type="button" onClick={() => setConfirmingBulk(false)} disabled={isBulkDeleting}>
                      {t("targets.cancel")}
                    </button>
                  </>
                ) : (
                  <button type="button" className="danger" onClick={() => setConfirmingBulk(true)}>
                    {isAdmin
                      ? t("targets.bulkDelete", { count: selectedIds.size })
                      : t("targets.bulkUnfollow", { count: selectedIds.size })}
                  </button>
                )}
              </div>
            )}
            {isAdmin && <TargetCompanyCsvImport onImported={loadCompanies} />}
          </div>
        </div>
        {confirmingBulk && (
          <p className="subtitle">
            {isAdmin
              ? t("targets.confirmBulkDeleteAdmin", { count: selectedIds.size })
              : t("targets.confirmBulkUnfollow", { count: selectedIds.size })}
          </p>
        )}
        {companies.length === 0 && <p className="subtitle">{t("targets.noCompaniesYet")}</p>}
        {companies.length > 0 && (
          <div className="field-row">
            <label>
              {t("targets.toolbar.searchLabel")}
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t("targets.toolbar.searchPlaceholder")}
              />
            </label>
            <label>
              {t("targets.toolbar.sortLabel")}
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value as typeof sortBy)}>
                <option value="name">{t("targets.toolbar.sortName")}</option>
                <option value="created">{t("targets.toolbar.sortCreated")}</option>
              </select>
            </label>
          </div>
        )}
        {visibleCompanies.length > 0 && (
          <div className="company-table-wrap">
            <table className="company-table">
              <thead>
                <tr>
                  <th className="checkbox-cell">
                    <input
                      type="checkbox"
                      checked={selectedIds.size === displayedCompanies.length}
                      onChange={toggleSelectAll}
                      aria-label={t("targets.selectAll")}
                    />
                  </th>
                  <th>{t("targets.columnCompany")}</th>
                  <th>{t("targets.columnStatus")}</th>
                  <th>{t("targets.columnTrackedFrom")}</th>
                  <th>{t("targets.columnActions")}</th>
                </tr>
              </thead>
              <tbody>
                {displayedCompanies.map((company) =>
                  editingId === company.id ? (
                    <tr key={company.id} className="editing">
                      <td colSpan={5}>
                        <form className="target-edit-form" onSubmit={(e) => saveEdit(e, company)}>
                          <div className="field-row">
                            <label>
                              {t("targets.companyName")}
                              <input
                                value={editName}
                                onChange={(e) => setEditName(e.target.value)}
                                required
                              />
                            </label>
                            <label>
                              {t("targets.industryOptional")}
                              <input value={editIndustry} onChange={(e) => setEditIndustry(e.target.value)} />
                            </label>
                          </div>
                          <label>
                            {t("targets.aliases")}
                            <TagInput
                              tags={editAliases}
                              onChange={setEditAliases}
                              placeholder={t("targets.aliasesPlaceholder")}
                            />
                            <span className="field-hint">{t("targets.aliasesHint")}</span>
                          </label>
                          <label>
                            {t("targets.contextTerms")}
                            <TagInput
                              tags={editContextTerms}
                              onChange={setEditContextTerms}
                              placeholder={t("targets.contextTermsPlaceholder")}
                            />
                            <span className="field-hint">{t("targets.contextTermsHint")}</span>
                          </label>
                          <label>
                            {t("targets.excludeTerms")}
                            <TagInput
                              tags={editExclusionTerms}
                              onChange={setEditExclusionTerms}
                              placeholder={t("targets.excludeTermsPlaceholder")}
                            />
                            <span className="field-hint">{t("targets.excludeTermsHint")}</span>
                          </label>
                          <SourceAllowlistField
                            value={editSourceAllowlist}
                            onChange={setEditSourceAllowlist}
                          />
                          <div className="actions">
                            <button type="submit" disabled={pendingId === company.id}>
                              {t("targets.save")}
                            </button>
                            <button type="button" onClick={cancelEdit} disabled={pendingId === company.id}>
                              {t("targets.cancel")}
                            </button>
                          </div>
                        </form>
                      </td>
                    </tr>
                  ) : (
                    <tr key={company.id} className={company.is_active ? "" : "inactive"}>
                      <td className="checkbox-cell">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(company.id)}
                          onChange={() => toggleSelect(company.id)}
                          aria-label={t("targets.selectCompany", { name: company.name })}
                        />
                      </td>
                      <td>
                        <strong>{company.name}</strong>
                        {company.industry && <span className="tag">{company.industry}</span>}
                        {company.is_muted && <span className="tag">{t("targets.muted")}</span>}
                        {company.keywords.length > 0 && (
                          <div className="keywords">{company.keywords.join(", ")}</div>
                        )}
                        {company.id === justCreatedId && company.backfilled_at === null && (
                          <div className="field-hint">{t("targets.backfilling")}</div>
                        )}
                      </td>
                      <td>{company.is_active ? t("targets.statusActive") : t("targets.statusPaused")}</td>
                      <td>
                        {company.followed_at ? formatDate(company.followed_at, { dateStyle: "medium" }) : "—"}
                      </td>
                      <td>
                        <div className="actions">
                          <button
                            type="button"
                            className="secondary"
                            disabled={
                              pendingId === company.id ||
                              isRunningIngestion ||
                              !company.is_active ||
                              noSourceEnabled
                            }
                            title={
                              noSourceEnabled
                                ? t("noNewsSource.blockedTooltip", { ns: "common" })
                                : !company.is_active
                                  ? t("targets.runNowBlockedPaused")
                                  : isRunningIngestion
                                    ? t("targets.runNowBlockedRunning")
                                    : t("targets.runNow")
                            }
                            onClick={() => runCompanyNow(company)}
                          >
                            {t("targets.runNow")}
                          </button>
                          {canEdit(company) && (
                            <button
                              type="button"
                              disabled={pendingId === company.id}
                              onClick={() => startEdit(company)}
                            >
                              {t("targets.edit")}
                            </button>
                          )}
                          {confirmingId === company.id ? (
                            <>
                              <button
                                type="button"
                                className="danger"
                                disabled={pendingId === company.id}
                                onClick={() => remove(company)}
                              >
                                {t("targets.confirmAction", { action: removeLabel().toLowerCase() })}
                              </button>
                              <button type="button" onClick={() => setConfirmingId(null)}>
                                {t("targets.cancel")}
                              </button>
                            </>
                          ) : (
                            <OverflowMenu
                              label={t("targets.rowActionsLabel", { name: company.name })}
                              disabled={pendingId === company.id}
                            >
                              {isAdmin &&
                                backfillEnabled &&
                                company.backfilled_at === null &&
                                company.id !== justCreatedId && (
                                  <button
                                    type="button"
                                    role="menuitem"
                                    onClick={() => triggerBackfill(company)}
                                    title={t("targets.backfillTitle")}
                                  >
                                    {t("targets.backfillHistory")}
                                  </button>
                                )}
                              <button type="button" role="menuitem" onClick={() => toggleMute(company)}>
                                {company.is_muted ? t("targets.unmute") : t("targets.mute")}
                              </button>
                              {canEdit(company) && (
                                <button type="button" role="menuitem" onClick={() => toggleActive(company)}>
                                  {company.is_active ? t("targets.pause") : t("targets.resume")}
                                </button>
                              )}
                              <hr />
                              <button
                                type="button"
                                role="menuitem"
                                className="danger"
                                title={confirmCopy(company)}
                                onClick={() => setConfirmingId(company.id)}
                              >
                                {removeLabel()}
                              </button>
                            </OverflowMenu>
                          )}
                        </div>
                        {confirmingId === company.id && <p className="subtitle">{confirmCopy(company)}</p>}
                      </td>
                    </tr>
                  )
                )}
                {visibleCompanies.length > TRACKED_COMPANIES_COLLAPSED_LIMIT && (
                  <tr className="table-toggle-row">
                    <td colSpan={5}>
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => setCompaniesExpanded((expanded) => !expanded)}
                      >
                        {companiesExpanded
                          ? t("targets.collapseCompanies")
                          : t("targets.expandCompanies", {
                              count: visibleCompanies.length - TRACKED_COMPANIES_COLLAPSED_LIMIT,
                            })}
                      </button>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel-card feed-toolbar">
        <div>
          <h2>{t("signals:feed.title")}</h2>
          <p className="subtitle">{t("signals:feed.subtitle")}</p>
        </div>
        <button
          type="button"
          onClick={handleRunIngestion}
          disabled={isRunningIngestion || !hasSomethingToFetch || noSourceEnabled}
          title={
            noSourceEnabled
              ? t("noNewsSource.blockedTooltip", { ns: "common" })
              : hasSomethingToFetch
                ? undefined
                : t("signals:feed.addCompanyOrThemeFirst")
          }
        >
          {isRunningIngestion
            ? t("signals:feed.fetching", { percent: ingestionStatus?.progress_percent ?? 0 })
            : t("signals:feed.fetchNewSignals")}
        </button>
      </div>

      {showSignalsChecklist && (
        <SetupChecklist
          hasCompanyProfile={hasCompanyProfile}
          hasTargetCompany={hasSomethingToFetch}
          hasSignals={signals.length > 0}
        />
      )}

      <div className="panel-card">
        <div className="field-row">
          <label>
            {t("signals:feed.targetCompany")}
            <select value={signalCompanyFilter} onChange={(e) => setSignalCompanyFilter(e.target.value)}>
              <option value="">{t("signals:feed.allCompanies")}</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("signals:feed.statusLabel")}
            <select
              value={signalStatusFilter}
              onChange={(e) => setSignalStatusFilter(e.target.value as SignalStatus | "")}
            >
              <option value="">{t("signals:status.all")}</option>
              {SIGNAL_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {t(`signals:status.${status}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="checkbox-label favorites-filter">
            <input
              type="checkbox"
              checked={signalFavoritedOnly}
              onChange={(e) => setSignalFavoritedOnly(e.target.checked)}
            />
            {t("signals:feed.favoritesOnly")}
          </label>
        </div>
        <div className="field-row">
          <label>
            {t("signals:feed.search")}
            <input
              value={signalSearchQuery}
              onChange={(e) => setSignalSearchQuery(e.target.value)}
              placeholder={t("signals:feed.searchPlaceholder")}
            />
          </label>
          <label>
            {t("signals:feed.sort")}
            <select value={signalSortOrder} onChange={(e) => setSignalSortOrder(e.target.value as SignalSortOrder)}>
              <option value="newest">{t("signals:feed.sortNewest")}</option>
              <option value="oldest">{t("signals:feed.sortOldest")}</option>
              <option value="relevance">{t("signals:feed.sortRelevance")}</option>
            </select>
          </label>
        </div>

        {signalsLoadError && <p className="error-text">{signalsLoadError}</p>}
        {isSignalsLoading && <Skeleton rows={4} />}
        {!isSignalsLoading && !signalsLoadError && visibleSignals.length === 0 && signals.length === 0 && signalFavoritedOnly && (
          <div className="empty-state">
            <EmptyStateIllustration />
            <p className="subtitle">{t("signals:feed.noFavoritesYet")}</p>
          </div>
        )}
        {!isSignalsLoading && !signalsLoadError && visibleSignals.length === 0 && signals.length === 0 && !signalFavoritedOnly && (
          <div className="empty-state">
            <EmptyStateIllustration />
            <p className="subtitle">{t("signals:feed.noSignalsYet")}</p>
          </div>
        )}
        {!isSignalsLoading && !signalsLoadError && visibleSignals.length === 0 && signals.length > 0 && (
          <p className="subtitle">{t("signals:feed.noSearchMatches")}</p>
        )}

        {!isSignalsLoading && visibleSignals.length > 0 && (
          <>
            <div className="feed-select-all">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={selectedSignalIds.size === visibleSignals.length}
                  onChange={toggleSignalSelectAll}
                />
                {t("signals:feed.selectAll")}
              </label>
              {selectedSignalIds.size > 0 && (
                <div className="bulk-actions">
                  <span className="subtitle">
                    {t("signals:feed.selectedCount", { count: selectedSignalIds.size })}
                  </span>
                  {STATUS_TRANSITION_VALUES.map((status) => (
                    <button
                      type="button"
                      key={status}
                      className="secondary"
                      title={t(`signals:transitionHints.${status}`, { defaultValue: "" })}
                      onClick={() => transitionSelectedSignals(status)}
                    >
                      {t(`signals:transitions.${status}`)}
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
                    checked: selectedSignalIds.has(signal.id),
                    onToggle: () => toggleSignalSelected(signal.id),
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
