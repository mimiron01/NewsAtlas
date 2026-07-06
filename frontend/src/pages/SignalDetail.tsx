import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { ARTICLE_SOURCE_LABELS } from "../api/types";
import type { Signal, SignalStatus } from "../api/types";
import Skeleton from "../components/Skeleton";
import { STATUS_TRANSITIONS } from "../constants/signalStatus";
import { useToast } from "../context/ToastContext";
import { usePageTitle } from "../hooks/usePageTitle";

const SIGNAL_TYPE_LABELS: Record<string, string> = {
  funding: "Funding",
  leadership_change: "Leadership change",
  expansion: "Expansion",
  hiring_surge: "Hiring surge",
  layoffs: "Layoffs",
  product_launch: "Product launch",
  partnership: "Partnership",
  competitor_mention: "Competitor mention",
  other: "Other",
};

const OUTREACH_CHANNELS: { key: "email" | "linkedin" | "call"; label: string }[] = [
  { key: "email", label: "Email" },
  { key: "linkedin", label: "LinkedIn" },
  { key: "call", label: "Call opener" },
];

export default function SignalDetail() {
  const { signalId } = useParams<{ signalId: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [signal, setSignal] = useState<Signal | null>(null);
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
          navigate("/", { replace: true });
          return;
        }
        setLoadError(err instanceof ApiError ? err.message : "Failed to load signal");
      });
  }, [signalId, navigate]);

  async function updateStatus(status: SignalStatus) {
    if (!signal) return;
    try {
      const updated = await api.patch<Signal>(`/signals/${signal.id}`, { status });
      setSignal(updated);
    } catch (err) {
      showToast(err instanceof ApiError ? err.message : "Failed to update status", "error");
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
      <Link to="/" className="link-button">
        ← Back to signals
      </Link>

      <div className="panel-card">
        <div className="signal-detail-badges">
          <span className={`status-badge status-${signal.status}`}>{signal.status}</span>
          {signal.relevance_score !== null && (
            <span className={`score-badge score-${signal.relevance_score}`}>
              Relevance {signal.relevance_score}/5
            </span>
          )}
          {signal.signal_type && (
            <span className="signal-type-badge">
              {SIGNAL_TYPE_LABELS[signal.signal_type] ?? signal.signal_type}
            </span>
          )}
          {signal.confidence && signal.confidence !== "high" && (
            <span className="confidence-badge" title="Model's confidence that this analysis is accurately grounded in the article">
              {signal.confidence} confidence
            </span>
          )}
          <span className="source-badge">{ARTICLE_SOURCE_LABELS[signal.article_source]}</span>
        </div>
        <h2>{signal.article_title}</h2>
        <p className="subtitle">
          {signal.target_company_name} · {signal.article_source_name}
          {signal.article_published_at &&
            ` · ${new Date(signal.article_published_at).toLocaleDateString()}`}
        </p>
        <p>
          <a href={signal.article_url} target="_blank" rel="noreferrer">
            View original article ↗
          </a>
        </p>

        <h3>Summary</h3>
        <p>{signal.summary}</p>

        <h3>Why it matters</h3>
        <p>{signal.business_relevance}</p>
        {signal.supporting_quote && (
          <blockquote className="supporting-quote">"{signal.supporting_quote}"</blockquote>
        )}

        {hasEntities && (
          <>
            <h3>Details</h3>
            <ul className="entities-list">
              {entities.amount && (
                <li>
                  <strong>Amount:</strong> {entities.amount}
                </li>
              )}
              {entities.people && entities.people.length > 0 && (
                <li>
                  <strong>People:</strong> {entities.people.join(", ")}
                </li>
              )}
              {entities.tags && entities.tags.length > 0 && (
                <li>
                  <strong>Tags:</strong> {entities.tags.join(", ")}
                </li>
              )}
            </ul>
          </>
        )}

        {(signal.article_external_sentiment || (signal.article_external_tags && signal.article_external_tags.length > 0)) && (
          <p className="field-hint">
            {signal.article_external_sentiment && (
              <>NewsData.io sentiment: {signal.article_external_sentiment}</>
            )}
            {signal.article_external_sentiment && signal.article_external_tags && signal.article_external_tags.length > 0 && " · "}
            {signal.article_external_tags && signal.article_external_tags.length > 0 && (
              <>NewsData.io tags: {signal.article_external_tags.join(", ")}</>
            )}
          </p>
        )}

        <h3>Outreach snippet</h3>
        <div className="snippet-tabs">
          {OUTREACH_CHANNELS.map((channel) => (
            <button
              type="button"
              key={channel.key}
              className={`snippet-tab${activeChannel === channel.key ? " active" : ""}`}
              onClick={() => setActiveChannel(channel.key)}
            >
              {channel.label}
            </button>
          ))}
        </div>
        <div className="snippet-box">{snippetForChannel(signal, activeChannel)}</div>
        <button type="button" onClick={copySnippet}>
          {copied ? "Copied!" : "Copy snippet"}
        </button>

        <div className="status-actions">
          {STATUS_TRANSITIONS.filter((t) => t.value !== signal.status).map((transition) => (
            <button
              type="button"
              key={transition.value}
              className="secondary"
              onClick={() => updateStatus(transition.value)}
            >
              {transition.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
