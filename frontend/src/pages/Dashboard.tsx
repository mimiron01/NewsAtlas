import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import type { DashboardSummary, IngestionRunStatus, Signal, TargetCompany, WorkspaceSettings } from "../api/types";
import Skeleton from "../components/Skeleton";
import SetupChecklist from "../components/SetupChecklist";
import SignalRow from "../components/SignalRow";
import EmptyStateIllustration from "../components/icons/EmptyStateIllustration";
import { useToast } from "../context/ToastContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { usePageTitle } from "../hooks/usePageTitle";

const POLL_INTERVAL_MS = 1500;

export default function Dashboard() {
  const { t } = useTranslation(["dashboard", "signals"]);
  usePageTitle(t("title"));
  const { showToast } = useToast();
  const isAdmin = useIsAdmin();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [ingestionStatus, setIngestionStatus] = useState<IngestionRunStatus | null>(null);
  // Tracks whether *this page load* actually watched a run go through "running" — so a
  // long-finished run from before the page was opened doesn't make it look like a fetch
  // just happened the moment you land here.
  const sawRunningRef = useRef(false);
  const isRunningIngestion = ingestionStatus?.status === "running";

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
    // /settings is admin-only; regular users can't view or fix the company profile anyway,
    // so skip the call rather than eat a 403 on every page load.
    if (isAdmin) {
      api.get<WorkspaceSettings>("/settings").then(setSettings).catch(() => undefined);
    }
  }, [isAdmin]);

  async function pollIngestionStatus() {
    try {
      const result = await api.get<IngestionRunStatus | null>("/ingestion/status");
      if (result?.status === "running") {
        sawRunningRef.current = true;
      }
      setIngestionStatus(result);
      if (sawRunningRef.current && result && result.status !== "running") {
        loadDashboard();
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

  async function handleRunIngestion() {
    try {
      const result = await api.post<IngestionRunStatus>("/ingestion/run-now");
      sawRunningRef.current = true;
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
  const hasAnySignals = Boolean(summary && (summary.top_signals.length > 0 || summary.new_signal_count > 0));
  const settingsReady = !isAdmin || settings !== null;
  const showChecklist = settingsReady && (!hasCompanyProfile || !hasTargetCompany || !hasAnySignals);

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
      <div className="panel-card feed-toolbar">
        <div>
          <h2>{t("title")}</h2>
          <p className="subtitle">{t("subtitle")}</p>
        </div>
        <button
          type="button"
          onClick={handleRunIngestion}
          disabled={isRunningIngestion || !hasTargetCompany}
          title={hasTargetCompany ? undefined : t("feed.addTargetCompanyFirst", { ns: "signals" })}
        >
          {isRunningIngestion
            ? t("feed.fetching", { ns: "signals", percent: ingestionStatus?.progress_percent ?? 0 })
            : t("feed.fetchNewSignals", { ns: "signals" })}
        </button>
      </div>

      {isRunningIngestion && ingestionStatus && (
        <div className="panel-card">
          <div className="progress-bar">
            <div className="progress-bar-fill" style={{ width: `${ingestionStatus.progress_percent}%` }} />
          </div>
        </div>
      )}

      <div className="dashboard-stats">
        <Link to="/signals?status=new" className="dashboard-stat">
          <strong>{summary.new_signal_count}</strong>
          <span>{t("stats.newSignals")}</span>
        </Link>
        <Link to="/signals?favorited=true" className="dashboard-stat">
          <strong>{summary.favorite_count}</strong>
          <span>{t("stats.favorites")}</span>
        </Link>
        <a href="#open-todos-panel" className="dashboard-stat">
          <strong>{summary.open_todo_count}</strong>
          <span>{t("stats.openTodos")}</span>
        </a>
        {summary.dismissed_signal_count + summary.skipped_article_count > 0 && (
          <Link to="/skipped" className="dashboard-stat">
            <strong>{summary.dismissed_signal_count + summary.skipped_article_count}</strong>
            <span>{t("stats.skipped")}</span>
          </Link>
        )}
      </div>

      {showChecklist && (
        <SetupChecklist
          hasCompanyProfile={hasCompanyProfile}
          hasTargetCompany={hasTargetCompany}
          hasSignals={hasAnySignals}
        />
      )}

      <div className="panel-card">
        <div className="feed-toolbar">
          <h3>{t("topSignals")}</h3>
          <Link to="/signals" className="link-button">
            {t("viewAllSignals")}
          </Link>
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
      </div>

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
