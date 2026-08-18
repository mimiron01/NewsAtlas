import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import { ARTICLE_SOURCE_LABELS } from "../api/types";
import type {
  IngestionRunStatus,
  PublicWorkspaceSettings,
  SignalStatus,
  TargetCompany,
  ThemeDuplicateNameDetail,
  ThemeMatch,
  ThemeWatch,
  ThemeWatchStats,
} from "../api/types";
import FavoriteButton from "../components/FavoriteButton";
import HelpTooltip from "../components/HelpTooltip";
import IngestionStatusPanel from "../components/IngestionStatusPanel";
import Modal from "../components/Modal";
import OverflowMenu from "../components/OverflowMenu";
import SourceAllowlistField from "../components/SourceAllowlistField";
import TagInput from "../components/TagInput";
import ThemeSourceSelector from "../components/ThemeSourceSelector";
import ThemeQueryPreviewPanel from "../components/ThemeQueryPreviewPanel";
import ThemeRunButton from "../components/ThemeRunButton";
import TopicTemplateGallery from "../components/TopicTemplateGallery";
import { STATUS_TRANSITION_VALUES } from "../constants/signalStatus";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { useIngestionStatus } from "../hooks/useIngestionStatus";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { usePageTitle } from "../hooks/usePageTitle";
import { useThemeQueryPreview } from "../hooks/useThemeQueryPreview";

const MATCH_STATUSES: SignalStatus[] = ["new", "reviewed", "archived", "dismissed"];

export default function ThemesPage() {
  const { t } = useTranslation(["themes", "signals"]);
  usePageTitle(t("themes:title"));
  const { showToast } = useToast();
  const { user } = useAuth();
  const isAdmin = useIsAdmin();

  const [themes, setThemes] = useState<ThemeWatch[]>([]);
  const [statsByThemeId, setStatsByThemeId] = useState<Record<string, ThemeWatchStats>>({});
  const [name, setName] = useState("");
  const [queryTerms, setQueryTerms] = useState<string[]>([]);
  const [excludeTerms, setExcludeTerms] = useState<string[]>([]);
  const [industry, setIndustry] = useState("");
  // null = inherit the workspace allowlist (see SourceAllowlistField).
  const [sourceAllowlist, setSourceAllowlist] = useState<string[] | null>(null);
  const [sourceDenylist, setSourceDenylist] = useState<string[]>([]);
  const [newsSources, setNewsSources] = useState<string[] | null>(null);
  const [country, setCountry] = useState("");
  const [language, setLanguage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAddThemeModalOpen, setIsAddThemeModalOpen] = useState(false);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editQueryTerms, setEditQueryTerms] = useState<string[]>([]);
  const [editExcludeTerms, setEditExcludeTerms] = useState<string[]>([]);
  const [editIndustry, setEditIndustry] = useState("");
  const [editSourceAllowlist, setEditSourceAllowlist] = useState<string[] | null>(null);
  const [editSourceDenylist, setEditSourceDenylist] = useState<string[]>([]);
  const [editNewsSources, setEditNewsSources] = useState<string[] | null>(null);
  const [editCountry, setEditCountry] = useState("");
  const [editLanguage, setEditLanguage] = useState("");
  // Set when POST /theme-watches 409s with a duplicate-name conflict (see
  // docs/topics-ux-improvements-planning.html §1.4) — surfaces the choice explicitly
  // instead of the old silent merge-by-name behavior.
  const [duplicateConflict, setDuplicateConflict] = useState<ThemeDuplicateNameDetail | null>(
    null
  );
  // List-level search/sort/bulk-select (§4.4 parity with the companies table) — the list
  // is small (capped by the workspace's active-topic ceiling), so this is all client-side
  // rather than server-side pagination/filtering.
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<"name" | "lastMatch" | "created">("name");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkConfirming, setBulkConfirming] = useState(false);
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);
  const [searchParams] = useSearchParams();
  // Deep link from the onboarding checklist (see
  // docs/topics-ux-improvements-planning.html §4.1) — opens straight into the gallery
  // instead of the blank create form, since a new user coming from "browse topic
  // templates" shouldn't have to find that action again themselves.
  const [showGallery, setShowGallery] = useState(searchParams.get("gallery") === "1");
  const [galleryDismissed, setGalleryDismissed] = useState(false);
  const [themesLoaded, setThemesLoaded] = useState(false);
  // Default view for a workspace with zero topics (see §4.2) — the gallery is more
  // useful than a blank form as the very first thing a new user sees here.
  const displayGallery =
    !galleryDismissed && (showGallery || (themesLoaded && themes.length === 0));

  const [matches, setMatches] = useState<ThemeMatch[]>([]);
  const [matchThemeFilter, setMatchThemeFilter] = useState("");
  const [matchStatusFilter, setMatchStatusFilter] = useState<SignalStatus | "">("");
  const [matchesLoading, setMatchesLoading] = useState(true);
  const [matchesError, setMatchesError] = useState<string | null>(null);
  const [trackingId, setTrackingId] = useState<string | null>(null);
  // Titles are clamped to 2 lines by default (see .signal-title) so row height stays
  // predictable regardless of title length; the "mehr anzeigen" toggle below only needs
  // to appear for rows that actually clamp, which this measures after each render.
  const [expandedMatchIds, setExpandedMatchIds] = useState<Set<string>>(new Set());
  const [overflowingMatchIds, setOverflowingMatchIds] = useState<Set<string>>(new Set());
  const titleRefs = useRef<Map<string, HTMLSpanElement>>(new Map());

  useEffect(() => {
    const next = new Set<string>();
    titleRefs.current.forEach((el, matchId) => {
      if (el.scrollHeight > el.clientHeight + 1) next.add(matchId);
    });
    setOverflowingMatchIds(next);
  }, [matches]);

  function toggleMatchExpanded(matchId: string) {
    setExpandedMatchIds((prev) => {
      const next = new Set(prev);
      if (next.has(matchId)) next.delete(matchId);
      else next.add(matchId);
      return next;
    });
  }

  const [publicSettings, setPublicSettings] = useState<PublicWorkspaceSettings | null>(null);
  // Resumes tracking a run already in flight (page reloaded mid-fetch, a scheduled run
  // happens to be going, or another user started one) rather than only reacting to this
  // browser's own click, and refreshes matches/topics once a run this page watched settles.
  const { ingestionStatus, setIngestionStatus, isRunning: isRunningIngestion } = useIngestionStatus(() => {
    loadMatches();
    loadThemes();
  });
  // Google News RSS is the only source topics can use, so everything on this page is inert
  // without it. Treated as available until the flags load, so the UI doesn't flash a
  // warning it may immediately retract.
  const googleNewsDisabled = publicSettings !== null && !publicSettings.google_news_rss_enabled;
  const cooldownSeconds = publicSettings?.manual_trigger_cooldown_seconds ?? 60;

  // Sources/Region & language start collapsed in the edit form too, unless the topic
  // being edited already has a non-default value in there — otherwise editing a topic
  // that deliberately overrides its sources would hide that override on every visit
  // (docs/platform-usability-onboarding-review.html F3). A brand-new topic (the create
  // form) always starts collapsed, since it can't have a non-default value yet.
  const editHasNonDefaultSources =
    editSourceAllowlist !== null || editSourceDenylist.length > 0 || editNewsSources !== null;
  const editHasNonDefaultRegion = editCountry !== "" || editLanguage !== "";

  const createPreview = useThemeQueryPreview({
    queryTerms,
    excludeTerms,
    sourceAllowlist,
    sourceDenylist,
    country,
    language,
    disabled: googleNewsDisabled,
  });
  const editPreview = useThemeQueryPreview({
    queryTerms: editQueryTerms,
    excludeTerms: editExcludeTerms,
    sourceAllowlist: editSourceAllowlist,
    sourceDenylist: editSourceDenylist,
    country: editCountry,
    language: editLanguage,
    disabled: googleNewsDisabled || editingId === null,
  });

  function canEdit(theme: ThemeWatch): boolean {
    return isAdmin || (user !== null && theme.created_by === user.id);
  }

  // Placeholders spell out what "leave blank" actually resolves to, so the inherited
  // edition is visible rather than implied by an empty box.
  function workspaceEditionPlaceholder(): string {
    return publicSettings
      ? t("themes:addTheme.inherits", { value: publicSettings.google_news_rss_country })
      : t("themes:addTheme.inheritsGeneric");
  }

  function workspaceLanguagePlaceholder(): string {
    return publicSettings
      ? t("themes:addTheme.inherits", { value: publicSettings.google_news_rss_language })
      : t("themes:addTheme.inheritsGeneric");
  }

  function loadThemes() {
    api
      .get<ThemeWatch[]>("/theme-watches")
      .then((result) => {
        setThemes(result);
        loadStats(result);
      })
      .catch((err) => showToast(err instanceof ApiError ? err.message : t("themes:loadFailed"), "error"))
      .finally(() => setThemesLoaded(true));
  }

  // One request per topic — fine at this scale, since active topics are capped
  // workspace-wide (default 10) by design (see docs/topics-ux-improvements-planning.html
  // §3.2). A per-topic failure is swallowed silently rather than surfacing an error
  // toast for what's a secondary, non-blocking piece of UI.
  function loadStats(forThemes: ThemeWatch[]) {
    Promise.all(
      forThemes.map((theme) =>
        api
          .get<ThemeWatchStats>(`/theme-watches/${theme.id}/stats`)
          .then((stats) => [theme.id, stats] as const)
          .catch(() => null)
      )
    ).then((results) => {
      setStatsByThemeId((prev) => {
        const next = { ...prev };
        for (const entry of results) {
          if (entry) next[entry[0]] = entry[1];
        }
        return next;
      });
    });
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

  useEffect(() => {
    api
      .get<PublicWorkspaceSettings>("/settings/public")
      .then(setPublicSettings)
      .catch(() => undefined);
  }, []);

  async function runTheme(theme: ThemeWatch) {
    setPendingId(theme.id);
    try {
      const result = await api.post<IngestionRunStatus>(`/theme-watches/${theme.id}/run-now`);
      setIngestionStatus(result);
      showToast(t("themes:run.startedToast", { name: theme.name }), "success");
      // Refreshes last_manual_run_at so this theme's cooldown countdown starts immediately.
      loadThemes();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("themes:run.failed"), "error");
    } finally {
      setPendingId(null);
    }
  }

  async function runFollowedThemes() {
    try {
      const result = await api.post<IngestionRunStatus>("/theme-watches/run-now");
      setIngestionStatus(result);
      showToast(t("themes:run.allStartedToast"), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("themes:run.allFailed"), "error");
    }
  }

  async function handleCancelIngestion() {
    if (!ingestionStatus) return;
    try {
      const result = await api.post<IngestionRunStatus>(`/ingestion/runs/${ingestionStatus.id}/cancel`);
      setIngestionStatus(result);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("signals:feed.ingestion.stopFailed"), "error");
    }
  }

  function resetCreateForm() {
    setName("");
    setQueryTerms([]);
    setExcludeTerms([]);
    setIndustry("");
    setSourceAllowlist(null);
    setSourceDenylist([]);
    setNewsSources(null);
    setCountry("");
    setLanguage("");
  }

  function buildCreatePayload(confirmMerge: boolean) {
    return {
      name,
      query_terms: queryTerms,
      exclude_terms: excludeTerms,
      industry: industry || null,
      google_news_source_allowlist: sourceAllowlist,
      google_news_source_denylist: sourceDenylist,
      news_sources: newsSources,
      // "" is the "workspace default" option; the backend stores it as null/inherit.
      google_news_country: country,
      google_news_language: language,
      confirm_merge: confirmMerge,
    };
  }

  async function handleAddTheme(event: FormEvent) {
    event.preventDefault();
    setDuplicateConflict(null);
    setIsSubmitting(true);
    try {
      await api.post<ThemeWatch>("/theme-watches", buildCreatePayload(false));
      resetCreateForm();
      setIsAddThemeModalOpen(false);
      showToast(t("themes:addedToast"), "success");
      loadThemes();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const detail = err.detail as ThemeDuplicateNameDetail | undefined;
        if (detail?.code === "duplicate_name") {
          setDuplicateConflict(detail);
          return;
        }
      }
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

  async function followExistingDuplicate() {
    setIsSubmitting(true);
    try {
      await api.post<ThemeWatch>("/theme-watches", buildCreatePayload(true));
      resetCreateForm();
      setDuplicateConflict(null);
      setIsAddThemeModalOpen(false);
      showToast(t("themes:addedToast"), "success");
      loadThemes();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("themes:addFailed"), "error");
    } finally {
      setIsSubmitting(false);
    }
  }

  function startEdit(theme: ThemeWatch) {
    setConfirmingId(null);
    setEditingId(theme.id);
    setEditName(theme.name);
    setEditQueryTerms(theme.query_terms);
    setEditExcludeTerms(theme.exclude_terms);
    setEditIndustry(theme.industry ?? "");
    setEditSourceAllowlist(theme.google_news_source_allowlist);
    setEditSourceDenylist(theme.google_news_source_denylist);
    setEditNewsSources(theme.news_sources);
    setEditCountry(theme.google_news_country ?? "");
    setEditLanguage(theme.google_news_language ?? "");
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
        exclude_terms: editExcludeTerms,
        industry: editIndustry || null,
        google_news_source_allowlist: editSourceAllowlist,
        google_news_source_denylist: editSourceDenylist,
        news_sources: editNewsSources,
        google_news_country: editCountry,
        google_news_language: editLanguage,
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

  async function toggleDigest(theme: ThemeWatch) {
    setPendingId(theme.id);
    try {
      await api.post(`/theme-watches/${theme.id}/digest`);
      loadThemes();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("themes:digest.updateFailed"), "error");
    } finally {
      setPendingId(null);
    }
  }

  function toggleSelected(themeId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(themeId)) next.delete(themeId);
      else next.add(themeId);
      return next;
    });
  }

  async function handleBulkDelete() {
    setIsBulkDeleting(true);
    try {
      await api.post("/theme-watches/bulk-delete", { theme_watch_ids: Array.from(selectedIds) });
      showToast(t("themes:bulk.deletedToast", { count: selectedIds.size }), "success");
      setSelectedIds(new Set());
      setBulkConfirming(false);
      loadThemes();
      loadMatches();
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("themes:bulk.removeFailed"), "error");
    } finally {
      setIsBulkDeleting(false);
    }
  }

  const visibleThemes = themes
    .filter((theme) => {
      const q = searchQuery.trim().toLowerCase();
      if (!q) return true;
      return (
        theme.name.toLowerCase().includes(q) ||
        (theme.industry ?? "").toLowerCase().includes(q) ||
        theme.query_terms.some((term) => term.toLowerCase().includes(q))
      );
    })
    .sort((a, b) => {
      if (sortBy === "name") return a.name.localeCompare(b.name);
      if (sortBy === "lastMatch") {
        const aTime = statsByThemeId[a.id]?.last_match_at ?? "";
        const bTime = statsByThemeId[b.id]?.last_match_at ?? "";
        return bTime.localeCompare(aTime);
      }
      // "created": no created_at on ThemeWatchResponse — approximate with list order
      // (the API already returns newest-first), so this is a no-op stable sort.
      return 0;
    });

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

  // A topic with no matches in this many days is flagged as possibly stale — proposed
  // default, not tuned against real usage yet (see
  // docs/topics-ux-improvements-planning.html §8's open questions). Only surfaced for
  // active topics; a paused one is expected to be quiet.
  const STALE_DAYS = 14;

  function renderThemeStats(theme: ThemeWatch) {
    const stats = statsByThemeId[theme.id];
    if (!stats) return null;
    if (stats.matches_last_30d === 0) {
      return <div className="field-hint">{t("themes:stats.noMatchesYet")}</div>;
    }
    const isStale =
      theme.is_active &&
      stats.last_match_at !== null &&
      Date.now() - new Date(stats.last_match_at).getTime() > STALE_DAYS * 24 * 60 * 60 * 1000;
    return (
      <div className="field-hint">
        {t("themes:stats.matches7d", { count: stats.matches_last_7d })}
        {stats.avg_relevance_score_30d !== null &&
          ` · ${t("themes:stats.avgRelevance", { score: stats.avg_relevance_score_30d.toFixed(1) })}`}
        {isStale && ` · ${t("themes:stats.stale")}`}
      </div>
    );
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

  async function toggleMatchFavorite(match: ThemeMatch) {
    const nextFavorited = !match.is_favorited;
    setMatches((prev) => prev.map((m) => (m.id === match.id ? { ...m, is_favorited: nextFavorited } : m)));
    try {
      const updated = nextFavorited
        ? await api.post<ThemeMatch>(`/theme-matches/${match.id}/favorite`)
        : await api.delete<ThemeMatch>(`/theme-matches/${match.id}/favorite`);
      setMatches((prev) => prev.map((m) => (m.id === match.id ? updated : m)));
    } catch (err) {
      setMatches((prev) => prev.map((m) => (m.id === match.id ? match : m)));
      showToast(err instanceof ApiError ? err.message : t("themes:matches.updateFailed"), "error");
    }
  }

  function handleTemplateApplied(_theme: ThemeWatch) {
    setShowGallery(false);
    showToast(t("themes:addedToast"), "success");
    loadThemes();
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
      {googleNewsDisabled && (
        <div className="panel-card warning-banner">
          <strong>{t("themes:sourceDisabled.title")}</strong>
          <p className="subtitle">
            {isAdmin ? t("themes:sourceDisabled.bodyAdmin") : t("themes:sourceDisabled.bodyMember")}
          </p>
          {isAdmin && (
            <Link to="/settings/sources" className="link-button">
              {t("themes:sourceDisabled.link")} →
            </Link>
          )}
        </div>
      )}

      <IngestionStatusPanel status={ingestionStatus} isAdmin={isAdmin} onCancel={handleCancelIngestion} />

      {displayGallery ? (
        <TopicTemplateGallery
          onApplied={handleTemplateApplied}
          onBack={() => {
            setShowGallery(false);
            setGalleryDismissed(true);
          }}
        />
      ) : (
        <>
      <div className="panel-card">
        <div className="feed-toolbar">
          <div>
            <h2>{t("themes:title")}</h2>
            <p className="subtitle">{t("themes:subtitle")}</p>
          </div>
          <div className="actions">
            <button type="button" onClick={() => setIsAddThemeModalOpen(true)}>
              {t("themes:addTheme.addButton")}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setShowGallery(true);
                setGalleryDismissed(false);
              }}
            >
              {t("themes:browseTemplates")}
            </button>
          </div>
        </div>
      </div>

      {isAddThemeModalOpen && (
        <Modal title={t("themes:addTheme.addButton")} onClose={() => setIsAddThemeModalOpen(false)}>
          <form onSubmit={handleAddTheme}>
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
            <div className="form-section">
              <h3 className="form-section-heading">{t("themes:addTheme.sections.criteria")}</h3>
              <label>
                <span className="label-text">
                  {t("themes:addTheme.queryTerms")}{" "}
                  <HelpTooltip content={t("themes:addTheme.queryTermsHint")} />
                </span>
                <TagInput
                  tags={queryTerms}
                  onChange={setQueryTerms}
                  placeholder={t("themes:addTheme.queryTermsPlaceholder")}
                />
              </label>
              <label>
                <span className="label-text">
                  {t("themes:addTheme.excludeTerms")}{" "}
                  <HelpTooltip content={t("themes:addTheme.excludeTermsHint")} />
                </span>
                <TagInput
                  tags={excludeTerms}
                  onChange={setExcludeTerms}
                  placeholder={t("themes:addTheme.excludeTermsPlaceholder")}
                />
              </label>
              <ThemeQueryPreviewPanel
                loading={createPreview.loading}
                result={createPreview.result}
                error={createPreview.error}
                googleNewsDisabled={googleNewsDisabled}
              />
            </div>
            <details className="form-section">
              <summary className="form-section-heading">{t("themes:addTheme.sections.sources")}</summary>
              <ThemeSourceSelector value={newsSources} onChange={setNewsSources} />
              <h4 className="form-section-subheading">{t("themes:addTheme.sections.domainFilters")}</h4>
              <SourceAllowlistField subject="topic" value={sourceAllowlist} onChange={setSourceAllowlist} />
              <label>
                <span className="label-text">
                  {t("themes:addTheme.sourceDenylist")}{" "}
                  <HelpTooltip content={t("themes:addTheme.sourceDenylistHint")} />
                </span>
                <TagInput
                  tags={sourceDenylist}
                  onChange={setSourceDenylist}
                  placeholder={t("themes:addTheme.sourceDenylistPlaceholder")}
                />
              </label>
            </details>
            <details className="form-section">
              <summary className="form-section-heading">{t("themes:addTheme.sections.region")}</summary>
              <div className="field-row">
                <label>
                  <span className="label-text">
                    {t("themes:addTheme.country")} <HelpTooltip content={t("themes:addTheme.editionHint")} />
                  </span>
                  <input
                    value={country}
                    onChange={(e) => setCountry(e.target.value)}
                    placeholder={workspaceEditionPlaceholder()}
                  />
                </label>
                <label>
                  {t("themes:addTheme.language")}
                  <input
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    placeholder={workspaceLanguagePlaceholder()}
                  />
                </label>
              </div>
            </details>
            {duplicateConflict && (
              <div className="panel-card warning-banner">
                <strong>{t("themes:duplicate.title")}</strong>
                <p className="subtitle">
                  {t("themes:duplicate.body", {
                    name,
                    terms: duplicateConflict.existing_query_terms.join(", "),
                  })}
                </p>
                <div className="actions">
                  <button type="button" disabled={isSubmitting} onClick={followExistingDuplicate}>
                    {t("themes:duplicate.followExisting")}
                  </button>
                  <button type="button" onClick={() => setDuplicateConflict(null)}>
                    {t("themes:duplicate.useDifferentName")}
                  </button>
                </div>
              </div>
            )}
            <button type="submit" disabled={isSubmitting || queryTerms.length === 0}>
              {t("themes:addTheme.addButton")}
            </button>
          </form>
        </Modal>
      )}

      <div className="panel-card">
        <h3>{t("themes:trackedThemes", { count: themes.length })}</h3>
        {themes.length === 0 && <p className="subtitle">{t("themes:noThemesYet")}</p>}
        {themes.length > 0 && (
          <div className="feed-toolbar">
            <div className="field-row">
              <label>
                {t("themes:toolbar.searchLabel")}
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={t("themes:toolbar.searchPlaceholder")}
                />
              </label>
              <label>
                {t("themes:toolbar.sortLabel")}
                <select value={sortBy} onChange={(e) => setSortBy(e.target.value as typeof sortBy)}>
                  <option value="name">{t("themes:toolbar.sortName")}</option>
                  <option value="lastMatch">{t("themes:toolbar.sortLastMatch")}</option>
                  <option value="created">{t("themes:toolbar.sortCreated")}</option>
                </select>
              </label>
            </div>
            <button
              type="button"
              onClick={runFollowedThemes}
              disabled={isRunningIngestion || googleNewsDisabled}
              title={googleNewsDisabled ? t("themes:sourceDisabled.title") : undefined}
            >
              {isRunningIngestion
                ? t("signals:feed.fetching", { percent: ingestionStatus?.progress_percent ?? 0 })
                : t("themes:run.allButton")}
            </button>
          </div>
        )}
        {visibleThemes.length > 0 && (
          <label className="checkbox-label select-all-row">
            <input
              type="checkbox"
              checked={selectedIds.size === visibleThemes.length}
              onChange={(e) =>
                setSelectedIds(e.target.checked ? new Set(visibleThemes.map((t) => t.id)) : new Set())
              }
            />
            {t("themes:bulk.selectAll")}
          </label>
        )}
        {selectedIds.size > 0 && (
          <div className="bulk-actions">
            <span className="subtitle">{t("themes:bulk.selectedCount", { count: selectedIds.size })}</span>
            {bulkConfirming ? (
              <>
                <button type="button" className="danger" disabled={isBulkDeleting} onClick={handleBulkDelete}>
                  {isAdmin
                    ? t("themes:bulk.delete", { count: selectedIds.size })
                    : t("themes:bulk.unfollow", { count: selectedIds.size })}
                </button>
                <button type="button" onClick={() => setBulkConfirming(false)}>
                  {t("themes:cancel")}
                </button>
              </>
            ) : (
              <button type="button" className="danger" onClick={() => setBulkConfirming(true)}>
                {isAdmin
                  ? t("themes:bulk.delete", { count: selectedIds.size })
                  : t("themes:bulk.unfollow", { count: selectedIds.size })}
              </button>
            )}
          </div>
        )}
        <ul className="target-list">
          {visibleThemes.map((theme) =>
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
                  <div className="form-section">
                    <h3 className="form-section-heading">{t("themes:addTheme.sections.criteria")}</h3>
                    <label>
                      <span className="label-text">
                        {t("themes:addTheme.queryTerms")}{" "}
                        <HelpTooltip content={t("themes:addTheme.queryTermsHint")} />
                      </span>
                      <TagInput
                        tags={editQueryTerms}
                        onChange={setEditQueryTerms}
                        placeholder={t("themes:addTheme.queryTermsPlaceholder")}
                      />
                    </label>
                    <label>
                      <span className="label-text">
                        {t("themes:addTheme.excludeTerms")}{" "}
                        <HelpTooltip content={t("themes:addTheme.excludeTermsHint")} />
                      </span>
                      <TagInput
                        tags={editExcludeTerms}
                        onChange={setEditExcludeTerms}
                        placeholder={t("themes:addTheme.excludeTermsPlaceholder")}
                      />
                    </label>
                    <ThemeQueryPreviewPanel
                      loading={editPreview.loading}
                      result={editPreview.result}
                      error={editPreview.error}
                      googleNewsDisabled={googleNewsDisabled}
                    />
                  </div>
                  <details className="form-section" open={editHasNonDefaultSources}>
                    <summary className="form-section-heading">{t("themes:addTheme.sections.sources")}</summary>
                    <ThemeSourceSelector value={editNewsSources} onChange={setEditNewsSources} />
                    <h4 className="form-section-subheading">{t("themes:addTheme.sections.domainFilters")}</h4>
                    <SourceAllowlistField
                      subject="topic"
                      value={editSourceAllowlist}
                      onChange={setEditSourceAllowlist}
                    />
                    <label>
                      <span className="label-text">
                        {t("themes:addTheme.sourceDenylist")}{" "}
                        <HelpTooltip content={t("themes:addTheme.sourceDenylistHint")} />
                      </span>
                      <TagInput
                        tags={editSourceDenylist}
                        onChange={setEditSourceDenylist}
                        placeholder={t("themes:addTheme.sourceDenylistPlaceholder")}
                      />
                    </label>
                  </details>
                  <details className="form-section" open={editHasNonDefaultRegion}>
                    <summary className="form-section-heading">{t("themes:addTheme.sections.region")}</summary>
                    <div className="field-row">
                      <label>
                        <span className="label-text">
                          {t("themes:addTheme.country")} <HelpTooltip content={t("themes:addTheme.editionHint")} />
                        </span>
                        <input
                          value={editCountry}
                          onChange={(e) => setEditCountry(e.target.value)}
                          placeholder={workspaceEditionPlaceholder()}
                        />
                      </label>
                      <label>
                        {t("themes:addTheme.language")}
                        <input
                          value={editLanguage}
                          onChange={(e) => setEditLanguage(e.target.value)}
                          placeholder={workspaceLanguagePlaceholder()}
                        />
                      </label>
                    </div>
                  </details>
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
                <div className="theme-row">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(theme.id)}
                    onChange={() => toggleSelected(theme.id)}
                    aria-label={theme.name}
                  />
                  <div className="theme-row-body">
                    <div className="theme-row-title">
                      <strong>{theme.name}</strong>
                      {theme.industry && <span className="tag">{theme.industry}</span>}
                      {theme.is_muted && <span className="tag">{t("themes:muted")}</span>}
                      {!theme.is_active && <span className="tag">{t("themes:paused")}</span>}
                      {(theme.google_news_country || theme.google_news_language) && (
                        <span className="tag">
                          {[theme.google_news_country, theme.google_news_language]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      )}
                    </div>
                    {theme.query_terms.length > 0 && (
                      <div className="keywords">{theme.query_terms.join(", ")}</div>
                    )}
                    {theme.exclude_terms.length > 0 && (
                      <div className="keywords subtitle">
                        −{theme.exclude_terms.join(", −")}
                      </div>
                    )}
                    {renderThemeStats(theme)}
                  </div>
                </div>
                <div className="actions">
                  <ThemeRunButton
                    theme={theme}
                    cooldownSeconds={cooldownSeconds}
                    isRunning={isRunningIngestion}
                    googleNewsDisabled={googleNewsDisabled}
                    isPending={pendingId === theme.id}
                    onRun={runTheme}
                  />
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
                    <OverflowMenu
                      label={t("themes:rowActionsLabel", { name: theme.name })}
                      disabled={pendingId === theme.id}
                    >
                      {canEdit(theme) && (
                        <button type="button" role="menuitem" onClick={() => startEdit(theme)}>
                          {t("themes:edit")}
                        </button>
                      )}
                      <button type="button" role="menuitem" onClick={() => toggleMute(theme)}>
                        {theme.is_muted ? t("themes:unmute") : t("themes:mute")}
                      </button>
                      <button type="button" role="menuitem" onClick={() => toggleDigest(theme)}>
                        {theme.include_in_digest ? t("themes:digest.exclude") : t("themes:digest.include")}
                      </button>
                      {canEdit(theme) && (
                        <button type="button" role="menuitem" onClick={() => toggleActive(theme)}>
                          {theme.is_active ? t("themes:pause") : t("themes:resume")}
                        </button>
                      )}
                      <hr />
                      <button
                        type="button"
                        role="menuitem"
                        className="danger"
                        title={confirmCopy(theme)}
                        onClick={() => setConfirmingId(theme.id)}
                      >
                        {removeLabel()}
                      </button>
                    </OverflowMenu>
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
                  <FavoriteButton isFavorited={match.is_favorited} onToggle={() => toggleMatchFavorite(match)} />
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
                    <div className="signal-row-content">
                      <strong>{match.theme_watch_name}</strong>
                      <div className="signal-title-row">
                        <a
                          className="signal-title"
                          href={match.url}
                          target="_blank"
                          rel="noreferrer"
                          ref={(el) => {
                            if (el) titleRefs.current.set(match.id, el);
                            else titleRefs.current.delete(match.id);
                          }}
                          data-expanded={expandedMatchIds.has(match.id) ? "" : undefined}
                        >
                          {match.title}
                        </a>
                      </div>
                      {overflowingMatchIds.has(match.id) && (
                        <button
                          type="button"
                          className="signal-title-toggle"
                          onClick={() => toggleMatchExpanded(match.id)}
                        >
                          {expandedMatchIds.has(match.id)
                            ? t("themes:matches.showLess")
                            : t("themes:matches.showMore")}
                        </button>
                      )}
                      {match.summary && <div className="subtitle">{match.summary}</div>}
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
      </>
      )}
    </div>
  );
}
