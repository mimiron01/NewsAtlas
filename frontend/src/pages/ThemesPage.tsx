import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import { ARTICLE_SOURCE_LABELS } from "../api/types";
import type { SignalStatus, TargetCompany, ThemeMatch, ThemeWatch } from "../api/types";
import TagInput from "../components/TagInput";
import { STATUS_TRANSITION_VALUES } from "../constants/signalStatus";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { usePageTitle } from "../hooks/usePageTitle";

const MATCH_STATUSES: SignalStatus[] = ["new", "reviewed", "archived", "dismissed"];

export default function ThemesPage() {
  const { t } = useTranslation(["themes", "signals"]);
  usePageTitle(t("themes:title"));
  const { showToast } = useToast();
  const { user } = useAuth();
  const isAdmin = useIsAdmin();

  const [themes, setThemes] = useState<ThemeWatch[]>([]);
  const [name, setName] = useState("");
  const [queryTerms, setQueryTerms] = useState<string[]>([]);
  const [industry, setIndustry] = useState("");
  const [sourceAllowlist, setSourceAllowlist] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editQueryTerms, setEditQueryTerms] = useState<string[]>([]);
  const [editIndustry, setEditIndustry] = useState("");
  const [editSourceAllowlist, setEditSourceAllowlist] = useState<string[]>([]);

  const [matches, setMatches] = useState<ThemeMatch[]>([]);
  const [matchThemeFilter, setMatchThemeFilter] = useState("");
  const [matchStatusFilter, setMatchStatusFilter] = useState<SignalStatus | "">("");
  const [matchesLoading, setMatchesLoading] = useState(true);
  const [matchesError, setMatchesError] = useState<string | null>(null);
  const [trackingId, setTrackingId] = useState<string | null>(null);

  function canEdit(theme: ThemeWatch): boolean {
    return isAdmin || (user !== null && theme.created_by === user.id);
  }

  function loadThemes() {
    api
      .get<ThemeWatch[]>("/theme-watches")
      .then(setThemes)
      .catch((err) => showToast(err instanceof ApiError ? err.message : t("themes:loadFailed"), "error"));
  }

  function loadMatches() {
    setMatchesLoading(true);
    const params = new URLSearchParams();
    if (matchThemeFilter) params.set("theme_id", matchThemeFilter);
    if (matchStatusFilter) params.set("status", matchStatusFilter);
    const query = params.toString();
    api
      .get<ThemeMatch[]>(`/theme-matches${query ? `?${query}` : ""}`)
      .then((result) => {
        setMatches(result);
        setMatchesError(null);
      })
      .catch((err) => setMatchesError(err instanceof ApiError ? err.message : t("themes:matches.loadFailed")))
      .finally(() => setMatchesLoading(false));
  }

  useEffect(loadThemes, [t]);
  useEffect(loadMatches, [matchThemeFilter, matchStatusFilter, t]);

  async function handleAddTheme(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await api.post<ThemeWatch>("/theme-watches", {
        name,
        query_terms: queryTerms,
        industry: industry || null,
        google_news_source_allowlist: sourceAllowlist,
      });
      setName("");
      setQueryTerms([]);
      setIndustry("");
      setSourceAllowlist([]);
      showToast(t("themes:addedToast"), "success");
      loadThemes();
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 400
          ? t("themes:activeCeilingReached")
          : err instanceof ApiError
            ? err.message
            : t("themes:addFailed");
      showToast(message, "error");
    } finally {
      setIsSubmitting(false);
    }
  }

  function startEdit(theme: ThemeWatch) {
    setConfirmingId(null);
    setEditingId(theme.id);
    setEditName(theme.name);
    setEditQueryTerms(theme.query_terms);
    setEditIndustry(theme.industry ?? "");
    setEditSourceAllowlist(theme.google_news_source_allowlist);
  }

  function cancelEdit() {
    setEditingId(null);
  }

  async function saveEdit(event: FormEvent, theme: ThemeWatch) {
    event.preventDefault();
    setPendingId(theme.id);
    try {
      await api.patch(`/theme-watches/${theme.id}`, {
        name: editName,
        query_terms: editQueryTerms,
        industry: editIndustry || null,
        google_news_source_allowlist: editSourceAllowlist,
      });
      setEditingId(null);
      showToast(t("themes:updatedToast", { name: editName }), "success");
      loadThemes();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("themes:updateFailed"), "error");
    } finally {
      setPendingId(null);
    }
  }

  async function toggleActive(theme: ThemeWatch) {
    setPendingId(theme.id);
    try {
      await api.patch(`/theme-watches/${theme.id}`, { is_active: !theme.is_active });
      loadThemes();
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 400
          ? t("themes:activeCeilingReached")
          : err instanceof ApiError
            ? err.message
            : t("themes:updateFailed");
      showToast(message, "error");
    } finally {
      setPendingId(null);
    }
  }

  async function toggleMute(theme: ThemeWatch) {
    setPendingId(theme.id);
    try {
      await api.post(`/theme-watches/${theme.id}/mute`);
      loadThemes();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("themes:updateFailed"), "error");
    } finally {
      setPendingId(null);
    }
  }

  async function remove(theme: ThemeWatch) {
    setPendingId(theme.id);
    try {
      await api.delete(`/theme-watches/${theme.id}`);
      showToast(
        isAdmin
          ? t("themes:deletedToast", { name: theme.name })
          : t("themes:unfollowedToast", { name: theme.name }),
        "success"
      );
      loadThemes();
      loadMatches();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("themes:removeFailed"), "error");
    } finally {
      setPendingId(null);
      setConfirmingId(null);
    }
  }

  function removeLabel(): string {
    return isAdmin ? t("themes:delete") : t("themes:unfollow");
  }

  function confirmCopy(theme: ThemeWatch): string {
    if (isAdmin) {
      return t("themes:confirmDeleteAdmin", { name: theme.name });
    }
    if (theme.follower_count <= 1) {
      return t("themes:confirmUnfollowOnly", { name: theme.name });
    }
    return t("themes:confirmUnfollowShared", { name: theme.name });
  }

  async function transitionMatch(match: ThemeMatch, status: SignalStatus) {
    try {
      const updated = await api.patch<ThemeMatch>(`/theme-matches/${match.id}`, { status });
      setMatches((prev) => prev.map((m) => (m.id === match.id ? updated : m)));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("themes:matches.updateFailed"), "error");
    }
  }

  async function trackCompany(match: ThemeMatch) {
    setTrackingId(match.id);
    try {
      const company = await api.post<TargetCompany>(`/theme-matches/${match.id}/track-company`);
      setMatches((prev) =>
        prev.map((m) =>
          m.id === match.id
            ? { ...m, matched_target_company_id: company.id, matched_target_company_name: company.name }
            : m
        )
      );
      showToast(t("themes:matches.trackedToast", { name: company.name }), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("themes:matches.trackCompanyFailed"), "error");
    } finally {
      setTrackingId(null);
    }
  }

  return (
    <div>
      <form className="panel-card" onSubmit={handleAddTheme}>
        <h2>{t("themes:title")}</h2>
        <p className="subtitle">{t("themes:subtitle")}</p>
        <div className="field-row">
          <label>
            {t("themes:addTheme.name")}
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            {t("themes:addTheme.industryOptional")}
            <input value={industry} onChange={(e) => setIndustry(e.target.value)} />
          </label>
        </div>
        <label>
          {t("themes:addTheme.queryTerms")}
          <TagInput
            tags={queryTerms}
            onChange={setQueryTerms}
            placeholder={t("themes:addTheme.queryTermsPlaceholder")}
          />
          <span className="field-hint">{t("themes:addTheme.queryTermsHint")}</span>
        </label>
        <label>
          {t("themes:addTheme.sourceAllowlist")}
          <TagInput
            tags={sourceAllowlist}
            onChange={setSourceAllowlist}
            placeholder={t("themes:addTheme.sourceAllowlistPlaceholder")}
          />
          <span className="field-hint">{t("themes:addTheme.sourceAllowlistHint")}</span>
        </label>
        <button type="submit" disabled={isSubmitting || queryTerms.length === 0}>
          {t("themes:addTheme.addButton")}
        </button>
      </form>

      <div className="panel-card">
        <h3>{t("themes:trackedThemes", { count: themes.length })}</h3>
        {themes.length === 0 && <p className="subtitle">{t("themes:noThemesYet")}</p>}
        <ul className="target-list">
          {themes.map((theme) =>
            editingId === theme.id ? (
              <li key={theme.id} className="editing">
                <form className="target-edit-form" onSubmit={(e) => saveEdit(e, theme)}>
                  <div className="field-row">
                    <label>
                      {t("themes:addTheme.name")}
                      <input value={editName} onChange={(e) => setEditName(e.target.value)} required />
                    </label>
                    <label>
                      {t("themes:addTheme.industryOptional")}
                      <input value={editIndustry} onChange={(e) => setEditIndustry(e.target.value)} />
                    </label>
                  </div>
                  <label>
                    {t("themes:addTheme.queryTerms")}
                    <TagInput
                      tags={editQueryTerms}
                      onChange={setEditQueryTerms}
                      placeholder={t("themes:addTheme.queryTermsPlaceholder")}
                    />
                    <span className="field-hint">{t("themes:addTheme.queryTermsHint")}</span>
                  </label>
                  <label>
                    {t("themes:addTheme.sourceAllowlist")}
                    <TagInput
                      tags={editSourceAllowlist}
                      onChange={setEditSourceAllowlist}
                      placeholder={t("themes:addTheme.sourceAllowlistPlaceholder")}
                    />
                    <span className="field-hint">{t("themes:addTheme.sourceAllowlistHint")}</span>
                  </label>
                  <div className="actions">
                    <button type="submit" disabled={pendingId === theme.id || editQueryTerms.length === 0}>
                      {t("themes:save")}
                    </button>
                    <button type="button" onClick={cancelEdit} disabled={pendingId === theme.id}>
                      {t("themes:cancel")}
                    </button>
                  </div>
                </form>
              </li>
            ) : (
              <li key={theme.id} className={theme.is_active ? "" : "inactive"}>
                <div>
                  <strong>{theme.name}</strong>
                  {theme.industry && <span className="tag">{theme.industry}</span>}
                  {theme.is_muted && <span className="tag">{t("themes:muted")}</span>}
                  {!theme.is_active && <span className="tag">{t("themes:paused")}</span>}
                  {theme.query_terms.length > 0 && (
                    <div className="keywords">{theme.query_terms.join(", ")}</div>
                  )}
                </div>
                <div className="actions">
                  {canEdit(theme) && (
                    <button type="button" disabled={pendingId === theme.id} onClick={() => startEdit(theme)}>
                      {t("themes:edit")}
                    </button>
                  )}
                  <button type="button" disabled={pendingId === theme.id} onClick={() => toggleMute(theme)}>
                    {theme.is_muted ? t("themes:unmute") : t("themes:mute")}
                  </button>
                  {canEdit(theme) && (
                    <button type="button" disabled={pendingId === theme.id} onClick={() => toggleActive(theme)}>
                      {theme.is_active ? t("themes:pause") : t("themes:resume")}
                    </button>
                  )}
                  {confirmingId === theme.id ? (
                    <>
                      <button
                        type="button"
                        className="danger"
                        disabled={pendingId === theme.id}
                        onClick={() => remove(theme)}
                      >
                        {t("themes:confirmAction", { action: removeLabel().toLowerCase() })}
                      </button>
                      <button type="button" onClick={() => setConfirmingId(null)}>
                        {t("themes:cancel")}
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="danger"
                      title={confirmCopy(theme)}
                      onClick={() => setConfirmingId(theme.id)}
                    >
                      {removeLabel()}
                    </button>
                  )}
                </div>
                {confirmingId === theme.id && <p className="subtitle">{confirmCopy(theme)}</p>}
              </li>
            )
          )}
        </ul>
      </div>

      <div className="panel-card">
        <h3>{t("themes:matches.title")}</h3>
        <p className="subtitle">{t("themes:matches.subtitle")}</p>
        <div className="field-row">
          <label>
            {t("themes:matches.themeFilter")}
            <select value={matchThemeFilter} onChange={(e) => setMatchThemeFilter(e.target.value)}>
              <option value="">{t("themes:matches.allThemes")}</option>
              {themes.map((theme) => (
                <option key={theme.id} value={theme.id}>
                  {theme.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("themes:matches.statusLabel")}
            <select
              value={matchStatusFilter}
              onChange={(e) => setMatchStatusFilter(e.target.value as SignalStatus | "")}
            >
              <option value="">{t("signals:status.all")}</option>
              {MATCH_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {t(`signals:status.${status}`)}
                </option>
              ))}
            </select>
          </label>
        </div>

        {matchesError && <p className="error-text">{matchesError}</p>}
        {!matchesLoading && !matchesError && matches.length === 0 && (
          <p className="subtitle">{t("themes:matches.noMatchesYet")}</p>
        )}

        {!matchesLoading && matches.length > 0 && (
          <ul className="signal-list">
            {matches.map((match) => (
              <li key={match.id}>
                <div className="signal-row">
                  <div className="signal-row-main">
                    <span className={`status-badge status-${match.status}`}>
                      {t(`signals:status.${match.status}`)}
                    </span>
                    {match.relevance_score !== null && (
                      <span className={`score-badge score-${match.relevance_score}`}>
                        {match.relevance_score}/5
                      </span>
                    )}
                    <span className="source-badge">{ARTICLE_SOURCE_LABELS[match.source]}</span>
                    {match.headline_only && (
                      <span className="limited-detail-badge" title={t("signals:limitedDetailTitle")}>
                        {t("signals:limitedDetail")}
                      </span>
                    )}
                    <div>
                      <strong>{match.theme_watch_name}</strong>
                      <a
                        className="signal-title"
                        href={match.url}
                        target="_blank"
                        rel="noreferrer"
                        style={{ display: "block" }}
                      >
                        {match.title}
                      </a>
                      <div className="subtitle">{match.summary}</div>
                      {match.extracted_company_name && (
                        <div className="field-hint">
                          {match.matched_target_company_id
                            ? t("themes:matches.alreadyTracked", {
                                name: match.matched_target_company_name ?? match.extracted_company_name,
                              })
                            : t("themes:matches.extractedCompany", { name: match.extracted_company_name })}
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="signal-row-actions">
                    {match.extracted_company_name && !match.matched_target_company_id && (
                      <button
                        type="button"
                        className="secondary"
                        disabled={trackingId === match.id}
                        onClick={() => trackCompany(match)}
                      >
                        {t("themes:matches.trackCompany")}
                      </button>
                    )}
                    {STATUS_TRANSITION_VALUES.filter((status) => status !== match.status).map((status) => (
                      <button
                        type="button"
                        key={status}
                        className="secondary"
                        onClick={() => transitionMatch(match, status)}
                      >
                        {t(`signals:transitions.${status}`)}
                      </button>
                    ))}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
