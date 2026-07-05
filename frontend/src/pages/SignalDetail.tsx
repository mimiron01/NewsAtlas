import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, ApiError } from "../api/client";
import type { Signal, SignalStatus } from "../api/types";
import Skeleton from "../components/Skeleton";
import { STATUS_TRANSITIONS } from "../constants/signalStatus";
import { useToast } from "../context/ToastContext";
import { usePageTitle } from "../hooks/usePageTitle";

export default function SignalDetail() {
  const { signalId } = useParams<{ signalId: string }>();
  const navigate = useNavigate();
  const { showToast } = useToast();
  const [signal, setSignal] = useState<Signal | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
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

  async function copySnippet() {
    if (!signal) return;
    await navigator.clipboard.writeText(signal.outreach_snippet);
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

  return (
    <div>
      <Link to="/" className="link-button">
        ← Back to signals
      </Link>

      <div className="panel-card">
        <span className={`status-badge status-${signal.status}`}>{signal.status}</span>
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

        <h3>Outreach snippet</h3>
        <div className="snippet-box">{signal.outreach_snippet}</div>
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
