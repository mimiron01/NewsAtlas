import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import type { BackfillTriggerResult, TargetCompany, WorkspaceSettings } from "../api/types";
import TagInput from "../components/TagInput";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { usePageTitle } from "../hooks/usePageTitle";

export default function SettingsTargets() {
  const { t } = useTranslation("settings");
  usePageTitle(t("targets.title"));
  const { showToast } = useToast();
  const { user } = useAuth();
  const isAdmin = useIsAdmin();
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [name, setName] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [industry, setIndustry] = useState("");
  const [sourceAllowlist, setSourceAllowlist] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [justCreatedId, setJustCreatedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editKeywords, setEditKeywords] = useState<string[]>([]);
  const [editIndustry, setEditIndustry] = useState("");
  const [editSourceAllowlist, setEditSourceAllowlist] = useState<string[]>([]);

  function canEdit(company: TargetCompany): boolean {
    return isAdmin || (user !== null && company.created_by === user.id);
  }
  // Only admins can read /settings, so backfill-related UI (the "backfilling..."
  // indicator and the manual trigger button) is admin-only — a regular user has no way
  // to know whether NewsData.io backfill is configured, and asking would just 403.
  const [backfillEnabled, setBackfillEnabled] = useState(false);

  function loadCompanies() {
    api
      .get<TargetCompany[]>("/target-companies")
      .then(setCompanies)
      .catch((err) => showToast(err instanceof ApiError ? err.message : t("targets.loadFailed"), "error"));
  }

  useEffect(loadCompanies, [t]);

  useEffect(() => {
    if (!isAdmin) return;
    api
      .get<WorkspaceSettings>("/settings")
      .then((settings) => setBackfillEnabled(settings.newsdata_enabled && settings.newsdata_backfill_days > 0))
      .catch(() => undefined);
  }, [isAdmin]);

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      const created = await api.post<TargetCompany>("/target-companies", {
        name,
        keywords,
        industry: industry || null,
        google_news_source_allowlist: sourceAllowlist,
      });
      setName("");
      setKeywords([]);
      setIndustry("");
      setSourceAllowlist([]);
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
    setEditKeywords(company.keywords);
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
        keywords: editKeywords,
        industry: editIndustry || null,
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

  return (
    <div>
      <form className="panel-card" onSubmit={handleAdd}>
        <h2>{t("targets.title")}</h2>
        <p className="subtitle">{t("targets.subtitle")}</p>
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
          {t("targets.keywords")}
          <TagInput
            tags={keywords}
            onChange={setKeywords}
            placeholder={t("targets.keywordsPlaceholder")}
          />
          <span className="field-hint">{t("targets.keywordsHint")}</span>
        </label>
        <label>
          {t("targets.sourceAllowlist")}
          <TagInput
            tags={sourceAllowlist}
            onChange={setSourceAllowlist}
            placeholder={t("targets.sourceAllowlistPlaceholder")}
          />
          <span className="field-hint">{t("targets.sourceAllowlistHint")}</span>
        </label>
        <button type="submit" disabled={isSubmitting}>
          {t("targets.addTargetCompany")}
        </button>
      </form>

      <div className="panel-card">
        <h3>{t("targets.trackedCompanies", { count: companies.length })}</h3>
        {companies.length === 0 && <p className="subtitle">{t("targets.noCompaniesYet")}</p>}
        <ul className="target-list">
          {companies.map((company) =>
            editingId === company.id ? (
              <li key={company.id} className="editing">
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
                    {t("targets.keywords")}
                    <TagInput
                      tags={editKeywords}
                      onChange={setEditKeywords}
                      placeholder={t("targets.keywordsPlaceholder")}
                    />
                    <span className="field-hint">{t("targets.keywordsHint")}</span>
                  </label>
                  <label>
                    {t("targets.sourceAllowlist")}
                    <TagInput
                      tags={editSourceAllowlist}
                      onChange={setEditSourceAllowlist}
                      placeholder={t("targets.sourceAllowlistPlaceholder")}
                    />
                    <span className="field-hint">{t("targets.sourceAllowlistHint")}</span>
                  </label>
                  <div className="actions">
                    <button type="submit" disabled={pendingId === company.id}>
                      {t("targets.save")}
                    </button>
                    <button type="button" onClick={cancelEdit} disabled={pendingId === company.id}>
                      {t("targets.cancel")}
                    </button>
                  </div>
                </form>
              </li>
            ) : (
              <li key={company.id} className={company.is_active ? "" : "inactive"}>
                <div>
                  <strong>{company.name}</strong>
                  {company.industry && <span className="tag">{company.industry}</span>}
                  {company.is_muted && <span className="tag">{t("targets.muted")}</span>}
                  {company.keywords.length > 0 && (
                    <div className="keywords">{company.keywords.join(", ")}</div>
                  )}
                  {company.id === justCreatedId && company.backfilled_at === null && (
                    <div className="field-hint">{t("targets.backfilling")}</div>
                  )}
                </div>
                <div className="actions">
                  {isAdmin && backfillEnabled && company.backfilled_at === null && company.id !== justCreatedId && (
                    <button
                      type="button"
                      disabled={pendingId === company.id}
                      onClick={() => triggerBackfill(company)}
                      title={t("targets.backfillTitle")}
                    >
                      {t("targets.backfillHistory")}
                    </button>
                  )}
                  {canEdit(company) && (
                    <button
                      type="button"
                      disabled={pendingId === company.id}
                      onClick={() => startEdit(company)}
                    >
                      {t("targets.edit")}
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={pendingId === company.id}
                    onClick={() => toggleMute(company)}
                  >
                    {company.is_muted ? t("targets.unmute") : t("targets.mute")}
                  </button>
                  {canEdit(company) && (
                    <button
                      type="button"
                      disabled={pendingId === company.id}
                      onClick={() => toggleActive(company)}
                    >
                      {company.is_active ? t("targets.pause") : t("targets.resume")}
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
                    <button
                      type="button"
                      className="danger"
                      title={confirmCopy(company)}
                      onClick={() => setConfirmingId(company.id)}
                    >
                      {removeLabel()}
                    </button>
                  )}
                </div>
                {confirmingId === company.id && <p className="subtitle">{confirmCopy(company)}</p>}
              </li>
            )
          )}
        </ul>
      </div>
    </div>
  );
}
