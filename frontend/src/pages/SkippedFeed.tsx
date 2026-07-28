import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import type { Signal, SignalStatus, SkippedArticle } from "../api/types";
import Skeleton from "../components/Skeleton";
import SignalRow from "../components/SignalRow";
import { useLocaleFormat } from "../hooks/useLocaleFormat";
import { useToast } from "../context/ToastContext";
import { useIsAdmin } from "../hooks/useIsAdmin";
import { usePageTitle } from "../hooks/usePageTitle";

// Consolidates the two "skipped" systems that were previously each buried in their own
// corner (a generic status filter for dismissed signals, an admin-only settings tab for
// triaged-out articles) into one page reachable from the dashboard (see
// docs/v1-release-roadmap.html §2.4).
export default function SkippedFeed() {
  const { t } = useTranslation(["signals", "settings"]);
  usePageTitle(t("skippedPage.title"));
  const { formatDate } = useLocaleFormat();
  const { showToast } = useToast();
  const isAdmin = useIsAdmin();
  const [signals, setSignals] = useState<Signal[] | null>(null);
  const [articles, setArticles] = useState<SkippedArticle[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [promotingId, setPromotingId] = useState<string | null>(null);

  function loadDismissedSignals() {
    api
      .get<Signal[]>("/signals?status=dismissed")
      .then(setSignals)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("skippedPage.loadFailed")));
  }

  function loadSkippedArticles() {
    if (!isAdmin) return;
    api
      .get<SkippedArticle[]>("/articles/skipped?reason=triaged_out")
      .then(setArticles)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("review.loadFailed", { ns: "settings" })));
  }

  useEffect(loadDismissedSignals, [t]);
  useEffect(loadSkippedArticles, [isAdmin, t]);

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
      // Any transition off "dismissed" (the only status this list ever shows) means it
      // no longer belongs in this list.
      setSignals((prev) => (prev ? prev.filter((s) => s.id !== id) : prev));
      showToast(t("skippedPage.restored", { title: updated.article_title }), "success");
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
        <h2>{t("skippedPage.title")}</h2>
        <p className="subtitle">{t("skippedPage.subtitle")}</p>
      </div>

      <div className="panel-card">
        <h3>{t("skippedPage.dismissedHeading")}</h3>
        {signals.length === 0 ? (
          <p className="subtitle">{t("skippedPage.noDismissed")}</p>
        ) : (
          <ul className="signal-list">
            {signals.map((signal) => (
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
          <h3>{t("skippedPage.skippedArticlesHeading")}</h3>
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
