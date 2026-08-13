import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import type {
  BackfillTriggerResult,
  IngestionRunStatus,
  PublicWorkspaceSettings,
  TargetCompany,
  TargetCompanyBulkDeleteResult,
  WorkspaceSettings,
} from "../api/types";
import IngestionStatusPanel from "../components/IngestionStatusPanel";
import Modal from "../components/Modal";
import OverflowMenu from "../components/OverflowMenu";
import SourceAllowlistField from "../components/SourceAllowlistField";
import TagInput from "../components/TagInput";
import TargetCompanyCsvImport from "../components/TargetCompanyCsvImport";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { useIngestionStatus } from "../hooks/useIngestionStatus";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { useLocaleFormat } from "../hooks/useLocaleFormat";
import { usePageTitle } from "../hooks/usePageTitle";

export default function SettingsTargets() {
  const { t } = useTranslation("settings");
  usePageTitle(t("targets.title"));
  const { showToast } = useToast();
  const { user } = useAuth();
  const isAdmin = useIsAdmin();
  const { formatDate } = useLocaleFormat();
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
  // browser's own click — same pattern as the Themes/Signals pages.
  const { ingestionStatus, setIngestionStatus, isRunning: isRunningIngestion } =
    useIngestionStatus();
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

  function canEdit(company: TargetCompany): boolean {
    return isAdmin || (user !== null && company.created_by === user.id);
  }
  // Only admins can read /settings, so backfill-related UI (the "backfilling..."
  // indicator and the manual trigger button) is admin-only — a regular user has no way
  // to know whether NewsData.io backfill is configured, and asking would just 403.
  const [backfillEnabled, setBackfillEnabled] = useState(false);
  const [publicSettings, setPublicSettings] = useState<PublicWorkspaceSettings | null>(null);

  function loadCompanies() {
    api
      .get<TargetCompany[]>("/target-companies")
      .then(setCompanies)
      .catch((err) => showToast(err instanceof ApiError ? err.message : t("targets.loadFailed"), "error"));
  }

  useEffect(loadCompanies, [t]);

  useEffect(() => {
    const validIds = new Set(companies.map((c) => c.id));
    setSelectedIds((prev) => {
      const next = new Set(Array.from(prev).filter((id) => validIds.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [companies]);

  useEffect(() => {
    if (!isAdmin) return;
    api
      .get<WorkspaceSettings>("/settings")
      .then((settings) => setBackfillEnabled(settings.newsdata_enabled && settings.newsdata_backfill_days > 0))
      .catch(() => undefined);
  }, [isAdmin]);

  useEffect(() => {
    // Readable by every user (unlike /settings above), so every user — not just admins —
    // learns whether a fetch can produce anything at all right now.
    api.get<PublicWorkspaceSettings>("/settings/public").then(setPublicSettings).catch(() => undefined);
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
    setSelectedIds((prev) =>
      prev.size === visibleCompanies.length ? new Set() : new Set(visibleCompanies.map((c) => c.id))
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
                      checked={selectedIds.size === visibleCompanies.length}
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
                {visibleCompanies.map((company) =>
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
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
