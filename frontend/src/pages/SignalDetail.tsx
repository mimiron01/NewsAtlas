import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import { ARTICLE_SOURCE_LABELS } from "../api/types";
import type { Signal, SignalStatus, SignalTodo } from "../api/types";
import FavoriteButton from "../components/FavoriteButton";
import Skeleton from "../components/Skeleton";
import TodoList from "../components/TodoList";
import { STATUS_TRANSITION_VALUES } from "../constants/signalStatus";
import { useToast } from "../context/ToastContext";
import { useLocaleFormat } from "../hooks/useLocaleFormat";
import { usePageTitle } from "../hooks/usePageTitle";

const OUTREACH_CHANNEL_KEYS: ("email" | "linkedin" | "call")[] = ["email", "linkedin", "call"];

export default function SignalDetail() {
  const { t } = useTranslation("signals");
  const { formatDate } = useLocaleFormat();
  const { signalId } = useParams<{ signalId: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [signal, setSignal] = useState<Signal | null>(null);
  const [todos, setTodos] = useState<SignalTodo[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeChannel, setActiveChannel] = useState<"email" | "linkedin" | "call">("email");
  const [copied, setCopied] = useState(false);

  usePageTitle(signal?.article_title);

  useEffect(() => {
    if (!signalId) return;
    api
      .get<Signal>(`/signals/${signalId}`)
      .then(setSignal)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          navigate("/signals", { replace: true });
          return;
        }
        setLoadError(err instanceof ApiError ? err.message : t("loadFailed"));
      });
    api
      .get<SignalTodo[]>(`/signals/${signalId}/todos`)
      .then(setTodos)
      .catch(() => undefined);
  }, [signalId, navigate, t]);

  async function updateStatus(status: SignalStatus) {
    if (!signal) return;
    const previousStatus = signal.status;
    try {
      const updated = await api.patch<Signal>(`/signals/${signal.id}`, { status });
      setSignal(updated);
      if (status === "dismissed") {
        showToast(t("dismissedToast"), "success", {
          label: t("undo"),
          onClick: () => updateStatus(previousStatus),
        });
      }
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("statusUpdateFailed"), "error");
    }
  }

  async function toggleFavorite() {
    if (!signal) return;
    const nextFavorited = !signal.is_favorited;
    setSignal({ ...signal, is_favorited: nextFavorited });
    try {
      const updated = nextFavorited
        ? await api.post<Signal>(`/signals/${signal.id}/favorite`)
        : await api.delete<Signal>(`/signals/${signal.id}/favorite`);
      setSignal(updated);
    } catch (err) {
      setSignal((prev) => (prev ? { ...prev, is_favorited: !nextFavorited } : prev));
      showToast(err instanceof ApiError ? err.message : t("favoriteUpdateFailed"), "error");
    }
  }

  async function addTodo(text: string) {
    if (!signal) return;
    try {
      const created = await api.post<SignalTodo>(`/signals/${signal.id}/todos`, { text });
      setTodos((prev) => [...prev, created]);
      setSignal((prev) => (prev ? { ...prev, open_todo_count: prev.open_todo_count + 1 } : prev));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("todoAddFailed"), "error");
    }
  }

  async function toggleTodo(todo: SignalTodo) {
    const nextDone = !todo.is_done;
    setTodos((prev) => prev.map((t) => (t.id === todo.id ? { ...t, is_done: nextDone } : t)));
    setSignal((prev) =>
      prev ? { ...prev, open_todo_count: prev.open_todo_count + (nextDone ? -1 : 1) } : prev
    );
    try {
      const updated = await api.patch<SignalTodo>(`/todos/${todo.id}`, { is_done: nextDone });
      setTodos((prev) => prev.map((t) => (t.id === todo.id ? updated : t)));
    } catch (err) {
      setTodos((prev) => prev.map((t) => (t.id === todo.id ? todo : t)));
      setSignal((prev) =>
        prev ? { ...prev, open_todo_count: prev.open_todo_count + (nextDone ? 1 : -1) } : prev
      );
      showToast(err instanceof ApiError ? err.message : t("todoUpdateFailed"), "error");
    }
  }

  async function deleteTodo(todo: SignalTodo) {
    setTodos((prev) => prev.filter((t) => t.id !== todo.id));
    if (!todo.is_done) {
      setSignal((prev) => (prev ? { ...prev, open_todo_count: prev.open_todo_count - 1 } : prev));
    }
    try {
      await api.delete(`/todos/${todo.id}`);
    } catch (err) {
      setTodos((prev) => [...prev, todo]);
      if (!todo.is_done) {
        setSignal((prev) => (prev ? { ...prev, open_todo_count: prev.open_todo_count + 1 } : prev));
      }
      showToast(err instanceof ApiError ? err.message : t("todoDeleteFailed"), "error");
    }
  }

  function snippetForChannel(current: Signal, channel: "email" | "linkedin" | "call"): string {
    if (channel === "email") return current.outreach_snippet_email;
    if (channel === "linkedin") return current.outreach_snippet_linkedin;
    return current.outreach_call_opener;
  }

  async function copySnippet() {
    if (!signal) return;
    await navigator.clipboard.writeText(snippetForChannel(signal, activeChannel));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (loadError) {
    return <p className="error-text">{loadError}</p>;
  }

  if (!signal) {
    return (
      <div className="panel-card">
        <Skeleton rows={5} />
      </div>
    );
  }

  const entities = signal.entities || {};
  const hasEntities = Boolean(entities.amount || entities.people?.length || entities.tags?.length);

  return (
    <div>
      <Link to="/signals" className="link-button">
        {t("backToSignals")}
      </Link>

      <div className="panel-card">
        <div className="signal-detail-badges">
          <FavoriteButton isFavorited={signal.is_favorited} onToggle={toggleFavorite} className="detail" />
          <span className={`status-badge status-${signal.status}`}>{t(`status.${signal.status}`)}</span>
          {signal.relevance_score !== null && (
            <span className={`score-badge score-${signal.relevance_score}`}>
              {t("relevance", { score: signal.relevance_score })}
            </span>
          )}
          {signal.signal_type && (
            <span className="signal-type-badge">
              {t(`signalTypes.${signal.signal_type}`, { defaultValue: signal.signal_type })}
            </span>
          )}
          {signal.confidence && signal.confidence !== "high" && (
            <span className="confidence-badge" title={t("confidenceTitle")}>
              {t("confidence", { level: t(`confidenceLevels.${signal.confidence}`) })}
            </span>
          )}
          <span className="source-badge">{ARTICLE_SOURCE_LABELS[signal.article_source]}</span>
          {signal.headline_only && (
            <span className="limited-detail-badge" title={t("limitedDetailTitle")}>
              {t("limitedDetail")}
            </span>
          )}
        </div>
        <h2>{signal.article_title}</h2>
        <p className="subtitle">
          {signal.target_company_name} · {signal.article_source_name}
          {signal.article_published_at && ` · ${formatDate(signal.article_published_at)}`}
        </p>
        <p>
          <a href={signal.article_url} target="_blank" rel="noreferrer">
            {t("viewOriginalArticle")}
          </a>
        </p>

        <h3>{t("summary")}</h3>
        <p>{signal.summary}</p>

        <h3>{t("whyItMatters")}</h3>
        <p>{signal.business_relevance}</p>
        {signal.supporting_quote && (
          <blockquote className="supporting-quote">"{signal.supporting_quote}"</blockquote>
        )}

        {hasEntities && (
          <>
            <h3>{t("details")}</h3>
            <ul className="entities-list">
              {entities.amount && (
                <li>
                  <strong>{t("amount")}:</strong> {entities.amount}
                </li>
              )}
              {entities.people && entities.people.length > 0 && (
                <li>
                  <strong>{t("people")}:</strong> {entities.people.join(", ")}
                </li>
              )}
              {entities.tags && entities.tags.length > 0 && (
                <li>
                  <strong>{t("tags")}:</strong> {entities.tags.join(", ")}
                </li>
              )}
            </ul>
          </>
        )}

        {(signal.article_external_sentiment || (signal.article_external_tags && signal.article_external_tags.length > 0)) && (
          <p className="field-hint">
            {signal.article_external_sentiment && (
              <>{t("newsdataSentiment", { sentiment: signal.article_external_sentiment })}</>
            )}
            {signal.article_external_sentiment && signal.article_external_tags && signal.article_external_tags.length > 0 && " · "}
            {signal.article_external_tags && signal.article_external_tags.length > 0 && (
              <>{t("newsdataTags", { tags: signal.article_external_tags.join(", ") })}</>
            )}
          </p>
        )}

        <h3>{t("outreachSnippet")}</h3>
        <div className="snippet-tabs">
          {OUTREACH_CHANNEL_KEYS.map((channel) => (
            <button
              type="button"
              key={channel}
              className={`snippet-tab${activeChannel === channel ? " active" : ""}`}
              onClick={() => setActiveChannel(channel)}
            >
              {t(`outreachChannels.${channel}`)}
            </button>
          ))}
        </div>
        <div className="snippet-box">{snippetForChannel(signal, activeChannel)}</div>
        <button type="button" onClick={copySnippet}>
          {copied ? t("copied") : t("copySnippet")}
        </button>

        <div className="status-actions">
          {STATUS_TRANSITION_VALUES.filter((status) => status !== signal.status).map((status) => (
            <button
              type="button"
              key={status}
              className="secondary"
              onClick={() => updateStatus(status)}
            >
              {t(`transitions.${status}`)}
            </button>
          ))}
        </div>
      </div>

      <div className="panel-card">
        <h3>{t("notesAndTodos")}</h3>
        <TodoList todos={todos} onAdd={addTodo} onToggle={toggleTodo} onDelete={deleteTodo} />
      </div>
    </div>
  );
}
