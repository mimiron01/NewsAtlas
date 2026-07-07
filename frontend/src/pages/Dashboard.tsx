import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, ApiError } from "../api/client";
import type { DashboardSummary, Signal, TargetCompany, WorkspaceSettings } from "../api/types";
import Skeleton from "../components/Skeleton";
import SetupChecklist from "../components/SetupChecklist";
import SignalRow from "../components/SignalRow";
import EmptyStateIllustration from "../components/icons/EmptyStateIllustration";
import { useToast } from "../context/ToastContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { usePageTitle } from "../hooks/usePageTitle";

export default function Dashboard() {
  usePageTitle("Dashboard");
  const { showToast } = useToast();
  const isAdmin = useIsAdmin();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
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
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Failed to load dashboard"))
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
      showToast(err instanceof ApiError ? err.message : "Failed to update favorite", "error");
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
      showToast(err instanceof ApiError ? err.message : "Failed to update todo", "error");
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
          <h2>Dashboard</h2>
          <p className="subtitle">Your newest and most relevant signals, at a glance.</p>
        </div>
      </div>

      <div className="dashboard-stats">
        <Link to="/signals?status=new" className="dashboard-stat">
          <strong>{summary.new_signal_count}</strong>
          <span>New signals</span>
        </Link>
        <Link to="/signals?favorited=true" className="dashboard-stat">
          <strong>{summary.favorite_count}</strong>
          <span>Favorites</span>
        </Link>
        <a href="#open-todos-panel" className="dashboard-stat">
          <strong>{summary.open_todo_count}</strong>
          <span>Open todos</span>
        </a>
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
          <h3>Top signals</h3>
          <Link to="/signals" className="link-button">
            View all signals →
          </Link>
        </div>
        {summary.top_signals.length === 0 ? (
          <div className="empty-state">
            <EmptyStateIllustration />
            <p className="subtitle">
              No open signals yet. Once signals come in, your newest and most relevant ones show up here.
            </p>
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
          <h3>Recent favorites</h3>
          {summary.recent_favorites.length === 0 ? (
            <p className="subtitle">You haven't favorited any signals yet. Star a signal to pin it here.</p>
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
          <h3>Open todos</h3>
          {summary.open_todos.length === 0 ? (
            <p className="subtitle">No open todos. Add one from a signal to track a follow-up.</p>
          ) : (
            <ul className="dashboard-mini-list">
              {summary.open_todos.map((todo) => (
                <li key={todo.id}>
                  <label className="checkbox-label todo-item-label">
                    <input
                      type="checkbox"
                      checked={false}
                      onChange={() => handleTodoDone(todo.id)}
                      aria-label={`Mark "${todo.text}" complete`}
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
