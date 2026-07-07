import { Link } from "react-router-dom";

import { ARTICLE_SOURCE_LABELS } from "../api/types";
import type { Signal, SignalStatus } from "../api/types";
import { STATUS_TRANSITIONS } from "../constants/signalStatus";
import FavoriteButton from "./FavoriteButton";

interface SignalRowProps {
  signal: Signal;
  onFavoriteToggle: (signal: Signal) => void;
  selection?: { checked: boolean; onToggle: () => void };
  onTransition?: (id: string, status: SignalStatus) => void;
}

export default function SignalRow({ signal, onFavoriteToggle, selection, onTransition }: SignalRowProps) {
  return (
    <li>
      <div className="signal-row">
        {selection && (
          <input
            type="checkbox"
            className="signal-checkbox"
            checked={selection.checked}
            onChange={selection.onToggle}
            aria-label={`Select ${signal.article_title}`}
          />
        )}
        <FavoriteButton isFavorited={signal.is_favorited} onToggle={() => onFavoriteToggle(signal)} />
        <Link to={`/signals/${signal.id}`} className="signal-row-link">
          <div className="signal-row-main">
            <span className={`status-badge status-${signal.status}`}>{signal.status}</span>
            {signal.relevance_score !== null && (
              <span className={`score-badge score-${signal.relevance_score}`}>
                {signal.relevance_score}/5
              </span>
            )}
            <span className="source-badge">{ARTICLE_SOURCE_LABELS[signal.article_source]}</span>
            {signal.open_todo_count > 0 && (
              <span className="todo-pill">
                {signal.open_todo_count} open {signal.open_todo_count === 1 ? "task" : "tasks"}
              </span>
            )}
            <div>
              <strong>{signal.target_company_name}</strong>
              <div className="signal-title">{signal.article_title}</div>
              <div className="subtitle">{signal.summary}</div>
            </div>
          </div>
        </Link>
        {onTransition && (
          <div className="signal-row-actions">
            {STATUS_TRANSITIONS.filter((t) => t.value !== signal.status).map((transition) => (
              <button
                type="button"
                key={transition.value}
                className="secondary"
                onClick={() => onTransition(signal.id, transition.value)}
              >
                {transition.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}
