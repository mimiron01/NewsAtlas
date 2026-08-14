import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import type {
  DashboardSummary,
  IngestionRunStatus,
  PublicWorkspaceSettings,
  Signal,
  TargetCompany,
  ThemeMatch,
  ThemeWatch,
  WorkspaceSettings,
} from "../api/types";
import Skeleton from "../components/Skeleton";
import SetupChecklist from "../components/SetupChecklist";
import SignalRow from "../components/SignalRow";
import FavoriteButton from "../components/FavoriteButton";
import IngestionStatusPanel from "../components/IngestionStatusPanel";
import EmptyStateIllustration from "../components/icons/EmptyStateIllustration";
import { useToast } from "../context/ToastContext";
import { useIngestionStatus } from "../hooks/useIngestionStatus";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { usePageTitle } from "../hooks/usePageTitle";

export default function Dashboard() {
  const { t } = useTranslation(["dashboard", "signals"]);
  usePageTitle(t("title"));
  const { showToast } = useToast();
  const isAdmin = useIsAdmin();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [themes, setThemes] = useState<ThemeWatch[]>([]);
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [publicSettings, setPublicSettings] = useState<PublicWorkspaceSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  function loadDashboard() {
    setIsLoading(true);
    api
      .get<DashboardSummary>("/dashboard")
      .then((result) => {
        setSummary(result);
        setLoadError(null);
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("loadFailed")))
      .finally(() => setIsLoading(false));
  }

  useEffect(() => {
    loadDashboard();
    api.get<TargetCompany[]>("/target-companies").then(setCompanies).catch(() => undefined);
    // Topics count as fetchable work too — a user tracking only topics must still be able
    // to start a run (see hasSomethingToFetch below).
    api.get<ThemeWatch[]>("/theme-watches").then(setThemes).catch(() => undefined);
    // Readable by every user (unlike /settings below), so every user — not just admins —
    // learns whether a fetch can produce anything at all right now.
    api.get<PublicWorkspaceSettings>("/settings/public").then(setPublicSettings).catch(() => undefined);
    // /settings is admin-only; regular users can't view or fix the company profile anyway,
    // so skip the call rather than eat a 403 on every page load.
    if (isAdmin) {
      api.get<WorkspaceSettings>("/settings").then(setSettings).catch(() => undefined);
    }
  }, [isAdmin]);

  // Treated as available until the flags load, so the UI doesn't flash a warning it may
  // immediately retract (same reasoning as ThemesPage's googleNewsDisabled).
  const noSourceEnabled = publicSettings !== null && !publicSettings.any_news_source_enabled;

  // Resumes tracking a run already in flight (e.g. the page was reloaded mid-fetch, or a
  // scheduled run happens to be running) instead of only ever reacting to this browser's
  // own button click, and refreshes the dashboard once a run this page watched settles.
  const { ingestionStatus, setIngestionStatus, isRunning: isRunningIngestion } =
    useIngestionStatus(loadDashboard);

  async function handleRunIngestion() {
    try {
      const result = await api.post<IngestionRunStatus>("/ingestion/run-now");
      setIngestionStatus(result);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("feed.ingestionStartFailed", { ns: "signals" }), "error");
    }
  }

  function patchSignalInLists(id: string, updated: Signal) {
    setSummary((prev) =>
      prev
        ? {
            ...prev,
            top_signals: prev.top_signals.map((s) => (s.id === id ? updated : s)),
            recent_favorites: prev.recent_favorites.map((s) => (s.id === id ? updated : s)),
          }
        : prev
    );
  }

  async function handleFavoriteToggle(signal: Signal) {
    const nextFavorited = !signal.is_favorited;
    const optimistic = { ...signal, is_favorited: nextFavorited };
    patchSignalInLists(signal.id, optimistic);
    setSummary((prev) =>
      prev ? { ...prev, favorite_count: prev.favorite_count + (nextFavorited ? 1 : -1) } : prev
    );
    try {
      const updated = nextFavorited
        ? await api.post<Signal>(`/signals/${signal.id}/favorite`)
        : await api.delete<Signal>(`/signals/${signal.id}/favorite`);
      patchSignalInLists(signal.id, updated);
    } catch (err) {
      patchSignalInLists(signal.id, signal);
      setSummary((prev) =>
        prev ? { ...prev, favorite_count: prev.favorite_count + (nextFavorited ? -1 : 1) } : prev
      );
      showToast(err instanceof ApiError ? err.message : t("favoriteUpdateFailed"), "error");
    }
  }

  function patchThemeMatchInLists(id: string, updated: ThemeMatch) {
    setSummary((prev) =>
      prev
        ? { ...prev, top_theme_matches: prev.top_theme_matches.map((m) => (m.id === id ? updated : m)) }
        : prev
    );
  }

  async function handleThemeMatchFavoriteToggle(match: ThemeMatch) {
    const nextFavorited = !match.is_favorited;
    patchThemeMatchInLists(match.id, { ...match, is_favorited: nextFavorited });
    try {
      const updated = nextFavorited
        ? await api.post<ThemeMatch>(`/theme-matches/${match.id}/favorite`)
        : await api.delete<ThemeMatch>(`/theme-matches/${match.id}/favorite`);
      patchThemeMatchInLists(match.id, updated);
    } catch (err) {
      patchThemeMatchInLists(match.id, match);
      showToast(err instanceof ApiError ? err.message : t("favoriteUpdateFailed"), "error");
    }
  }

  async function handleTodoDone(todoId: string) {
    let removed: DashboardSummary["open_todos"][number] | undefined;
    setSummary((prev) => {
      if (!prev) return prev;
      removed = prev.open_todos.find((t) => t.id === todoId);
      return {
        ...prev,
        open_todos: prev.open_todos.filter((t) => t.id !== todoId),
        open_todo_count: Math.max(0, prev.open_todo_count - 1),
      };
    });
    try {
      await api.patch(`/todos/${todoId}`, { is_done: true });
    } catch (err) {
      setSummary((prev) =>
        prev && removed
          ? { ...prev, open_todos: [removed, ...prev.open_todos], open_todo_count: prev.open_todo_count + 1 }
          : prev
      );
      showToast(err instanceof ApiError ? err.message : t("todoUpdateFailed"), "error");
    }
  }

  // Non-admins can't view or fix the company profile (admin-only), so treat it as
  // satisfied for them rather than gating the checklist on data they'll never fetch.
  const hasCompanyProfile = isAdmin ? Boolean(settings?.offering_description.trim()) : true;
  const hasTargetCompany = companies.length > 0;
  const hasTheme = themes.length > 0;
  // A run fetches for companies *and* topics, so either one on its own is enough work to
  // justify the button. Gating on companies alone left a topics-only user unable to fetch
  // anything at all.
  const hasSomethingToFetch = hasTargetCompany || hasTheme;
  const hasAnySignals = Boolean(
    summary &&
      (summary.top_signals.length > 0 ||
        summary.new_signal_count > 0 ||
        summary.top_theme_matches.length > 0 ||
        summary.new_theme_match_count > 0)
  );
  const settingsReady = !isAdmin || settings !== null;
  const showChecklist = settingsReady && (!hasCompanyProfile || !hasSomethingToFetch || !hasAnySignals);

  if (loadError) {
    return <p className="error-text">{loadError}</p>;
  }

  if (isLoading || !summary) {
    return (
      <div className="panel-card">
        <Skeleton rows={5} />
      </div>
    );
  }

  return (
    <div>
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

      <div className="panel-card feed-toolbar">
        <div>
          <h2>{t("title")}</h2>
          <p className="subtitle">{t("subtitle")}</p>
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
                : t("feed.addCompanyOrThemeFirst", { ns: "signals" })
          }
        >
          {isRunningIngestion
            ? t("feed.fetching", { ns: "signals", percent: ingestionStatus?.progress_percent ?? 0 })
            : t("feed.fetchNewSignals", { ns: "signals" })}
        </button>
      </div>

      <IngestionStatusPanel status={ingestionStatus} isAdmin={isAdmin} />

      <div className="dashboard-stats">
        <Link to="/signals?status=new" className="dashboard-stat">
          <strong>{summary.new_signal_count}</strong>
          <span>{t("stats.newSignals")}</span>
        </Link>
        <Link to="/signals?favorited=true" className="dashboard-stat">
          <strong>{summary.favorite_count}</strong>
          <span>{t("stats.favorites")}</span>
        </Link>
        {hasTheme && (
          <Link to="/themes" className="dashboard-stat">
            <strong>{summary.new_theme_match_count}</strong>
            <span>{t("stats.newThemeMatches")}</span>
          </Link>
        )}
        <a href="#open-todos-panel" className="dashboard-stat">
          <strong>{summary.open_todo_count}</strong>
          <span>{t("stats.openTodos")}</span>
        </a>
        <Link to="/archive" className="dashboard-stat">
          <strong>
            {summary.archived_signal_count + summary.dismissed_signal_count + summary.skipped_article_count}
          </strong>
          <span>{t("stats.archive")}</span>
        </Link>
      </div>

      {showChecklist && (
        <SetupChecklist
          hasCompanyProfile={hasCompanyProfile}
          hasTargetCompany={hasSomethingToFetch}
          hasSignals={hasAnySignals}
        />
      )}

      <div className="panel-card">
        <div className="feed-toolbar">
          <h3>{t("topSignals")}</h3>
        </div>
        {summary.top_signals.length === 0 ? (
          <div className="empty-state">
            <EmptyStateIllustration />
            <p className="subtitle">{t("noSignalsYet")}</p>
          </div>
        ) : (
          <ul className="signal-list">
            {summary.top_signals.map((signal) => (
              <SignalRow key={signal.id} signal={signal} onFavoriteToggle={handleFavoriteToggle} />
            ))}
          </ul>
        )}
        <Link to="/signals" className="link-button dashboard-panel-footer-link">
          {t("viewAllSignals")}
        </Link>
      </div>

      {/* Only rendered for users who actually follow a topic, so a company-only
          workspace's dashboard is unchanged. */}
      {hasTheme && (
        <div className="panel-card">
          <div className="feed-toolbar">
            <h3>{t("topThemeMatches")}</h3>
          </div>
          {summary.top_theme_matches.length === 0 ? (
            <p className="subtitle">{t("noThemeMatchesYet")}</p>
          ) : (
            <ul className="dashboard-mini-list">
              {summary.top_theme_matches.map((match) => (
                <li key={match.id}>
                  <div className="dashboard-mini-list-row">
                    <FavoriteButton
                      isFavorited={match.is_favorited}
                      onToggle={() => handleThemeMatchFavoriteToggle(match)}
                      className="detail"
                    />
                    <a href={match.url} target="_blank" rel="noreferrer">
                      {match.title}
                    </a>
                  </div>
                  <span className="subtitle">
                    {match.theme_watch_name}
                    {match.relevance_score !== null && ` · ${match.relevance_score}/5`}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <Link to="/themes" className="link-button dashboard-panel-footer-link">
            {t("viewAllThemeMatches")}
          </Link>
        </div>
      )}

      <div className="dashboard-panels">
        <div className="panel-card">
          <h3>{t("recentFavorites")}</h3>
          {summary.recent_favorites.length === 0 ? (
            <p className="subtitle">{t("noFavoritesYet")}</p>
          ) : (
            <ul className="dashboard-mini-list">
              {summary.recent_favorites.map((signal) => (
                <li key={signal.id}>
                  <Link to={`/signals/${signal.id}`}>{signal.article_title}</Link>
                  <span className="subtitle">{signal.target_company_name}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="panel-card" id="open-todos-panel">
          <h3>{t("openTodosHeading")}</h3>
          {summary.open_todos.length === 0 ? (
            <p className="subtitle">{t("noOpenTodos")}</p>
          ) : (
            <ul className="dashboard-mini-list">
              {summary.open_todos.map((todo) => (
                <li key={todo.id}>
                  <label className="checkbox-label todo-item-label">
                    <input
                      type="checkbox"
                      checked={false}
                      onChange={() => handleTodoDone(todo.id)}
                      aria-label={t("markTodoComplete", { text: todo.text })}
                    />
                    <span className="todo-text">{todo.text}</span>
                  </label>
                  <Link to={`/signals/${todo.signal_id}`} className="subtitle">
                    {todo.target_company_name} · {todo.article_title}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
