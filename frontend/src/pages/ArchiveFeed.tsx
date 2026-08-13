import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import type { Signal, SignalStatus, SkippedArticle } from "../api/types";
import Skeleton from "../components/Skeleton";
import SignalRow from "../components/SignalRow";
import { useLocaleFormat } from "../hooks/useLocaleFormat";
import { useToast } from "../context/ToastContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { usePageTitle } from "../hooks/usePageTitle";

type ArchiveFilter = "all" | "archived" | "dismissed";

// Consolidates archived and dismissed signals (see docs/archive-dismiss-ux-planning.html)
// plus the admin-only triaged-out articles queue into one page, so "where did my
// archived/skipped stuff go" has one answer instead of several.
export default function ArchiveFeed() {
  const { t } = useTranslation(["signals", "settings"]);
  usePageTitle(t("archivePage.title"));
  const { formatDate } = useLocaleFormat();
  const { showToast } = useToast();
  const isAdmin = useIsAdmin();
  const [signals, setSignals] = useState<Signal[] | null>(null);
  const [filter, setFilter] = useState<ArchiveFilter>("all");
  const [articles, setArticles] = useState<SkippedArticle[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [promotingId, setPromotingId] = useState<string | null>(null);

  function loadArchivedSignals() {
    Promise.all([
      api.get<Signal[]>("/signals?status=archived"),
      api.get<Signal[]>("/signals?status=dismissed"),
    ])
      .then(([archived, dismissed]) =>
        setSignals(
          [...archived, ...dismissed].sort(
            (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
          )
        )
      )
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("archivePage.loadFailed")));
  }

  function loadSkippedArticles() {
    if (!isAdmin) return;
    api
      .get<SkippedArticle[]>("/articles/skipped?reason=triaged_out")
      .then(setArticles)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("review.loadFailed", { ns: "settings" })));
  }

  useEffect(loadArchivedSignals, [t]);
  useEffect(loadSkippedArticles, [isAdmin, t]);

  const visibleSignals = useMemo(
    () => (signals ?? []).filter((s) => filter === "all" || s.status === filter),
    [signals, filter]
  );

  async function handleFavoriteToggle(signal: Signal) {
    const nextFavorited = !signal.is_favorited;
    try {
      const updated = nextFavorited
        ? await api.post<Signal>(`/signals/${signal.id}/favorite`)
        : await api.delete<Signal>(`/signals/${signal.id}/favorite`);
      setSignals((prev) => (prev ? prev.map((s) => (s.id === signal.id ? updated : s)) : prev));
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("favoriteUpdateFailed"), "error");
    }
  }

  async function transitionSignal(id: string, status: SignalStatus) {
    try {
      const updated = await api.patch<Signal>(`/signals/${id}`, { status });
      // Any transition away from archived/dismissed (the only statuses this list ever
      // shows) means it no longer belongs here.
      setSignals((prev) => (prev ? prev.filter((s) => s.id !== id) : prev));
      showToast(t("archivePage.restored", { title: updated.article_title }), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("feed.signalUpdateFailed"), "error");
    }
  }

  async function handlePromote(article: SkippedArticle) {
    setPromotingId(article.id);
    try {
      await api.post(`/articles/${article.id}/create-signal`);
      setArticles((prev) => (prev ? prev.filter((a) => a.id !== article.id) : prev));
      showToast(t("review.promoted", { ns: "settings", title: article.title }), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("review.promoteFailed", { ns: "settings" }), "error");
    } finally {
      setPromotingId(null);
    }
  }

  if (loadError) {
    return <p className="error-text">{loadError}</p>;
  }

  if (signals === null) {
    return (
      <div className="panel-card">
        <Skeleton rows={4} />
      </div>
    );
  }

  return (
    <div>
      <div className="panel-card">
        <h2>{t("archivePage.title")}</h2>
        <p className="subtitle">{t("archivePage.subtitle")}</p>
      </div>

      <div className="panel-card">
        <label>
          {t("archivePage.filterLabel")}
          <select value={filter} onChange={(e) => setFilter(e.target.value as ArchiveFilter)}>
            <option value="all">{t("archivePage.filterAll")}</option>
            <option value="archived">{t("archivePage.filterArchived")}</option>
            <option value="dismissed">{t("archivePage.filterDismissed")}</option>
          </select>
        </label>
        {visibleSignals.length === 0 ? (
          <p className="subtitle">{t("archivePage.empty")}</p>
        ) : (
          <ul className="signal-list">
            {visibleSignals.map((signal) => (
              <SignalRow
                key={signal.id}
                signal={signal}
                onFavoriteToggle={handleFavoriteToggle}
                onTransition={transitionSignal}
              />
            ))}
          </ul>
        )}
      </div>

      {isAdmin && (
        <div className="panel-card">
          <h3>{t("archivePage.skippedArticlesHeading")}</h3>
          <p className="subtitle">{t("review.subtitle", { ns: "settings" })}</p>
          {articles === null ? (
            <Skeleton rows={3} />
          ) : articles.length === 0 ? (
            <p className="subtitle">{t("review.empty", { ns: "settings" })}</p>
          ) : (
            <ul className="target-list">
              {articles.map((article) => (
                <li key={article.id}>
                  <div>
                    <a href={article.url} target="_blank" rel="noreferrer">
                      <strong>{article.title}</strong>
                    </a>
                    <span className="tag">{article.target_company_name}</span>
                    <span className="tag">{article.source_name}</span>
                    {article.published_at && (
                      <span className="tag">{formatDate(article.published_at, { dateStyle: "short" })}</span>
                    )}
                    {article.headline_only && (
                      <span className="tag" title={t("review.limitedDetailTitle", { ns: "settings" })}>
                        {t("review.limitedDetail", { ns: "settings" })}
                      </span>
                    )}
                    {article.triage_reason && (
                      <p className="field-hint">{t("review.reason", { ns: "settings", reason: article.triage_reason })}</p>
                    )}
                  </div>
                  <div className="actions">
                    <button
                      type="button"
                      disabled={promotingId === article.id}
                      onClick={() => handlePromote(article)}
                    >
                      {promotingId === article.id ? t("review.promoting", { ns: "settings" }) : t("review.promote", { ns: "settings" })}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
