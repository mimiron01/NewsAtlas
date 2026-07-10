import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../../api/client";
import type { SkippedArticle } from "../../api/types";
import Skeleton from "../../components/Skeleton";
import { useToast } from "../../context/ToastContext";
import { useLocaleFormat } from "../../hooks/useLocaleFormat";

export default function ReviewTab() {
  const { t } = useTranslation("settings");
  const { formatDate } = useLocaleFormat();
  const { showToast } = useToast();
  const [articles, setArticles] = useState<SkippedArticle[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [promotingId, setPromotingId] = useState<string | null>(null);

  function load() {
    api
      .get<SkippedArticle[]>("/articles/skipped?reason=triaged_out")
      .then(setArticles)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : t("review.loadFailed")));
  }

  useEffect(load, [t]);

  async function handlePromote(article: SkippedArticle) {
    setPromotingId(article.id);
    try {
      await api.post(`/articles/${article.id}/create-signal`);
      setArticles((prev) => (prev ? prev.filter((a) => a.id !== article.id) : prev));
      showToast(t("review.promoted", { title: article.title }), "success");
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : t("review.promoteFailed"), "error");
    } finally {
      setPromotingId(null);
    }
  }

  if (loadError) {
    return <p className="error-text">{loadError}</p>;
  }

  if (articles === null) {
    return (
      <div className="panel-card">
        <Skeleton rows={4} />
      </div>
    );
  }

  return (
    <div className="panel-card">
      <h2>{t("review.title")}</h2>
      <p className="subtitle">{t("review.subtitle")}</p>

      {articles.length === 0 && <p className="subtitle">{t("review.empty")}</p>}

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
              {article.triage_reason && (
                <p className="field-hint">{t("review.reason", { reason: article.triage_reason })}</p>
              )}
            </div>
            <div className="actions">
              <button
                type="button"
                disabled={promotingId === article.id}
                onClick={() => handlePromote(article)}
              >
                {promotingId === article.id ? t("review.promoting") : t("review.promote")}
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
