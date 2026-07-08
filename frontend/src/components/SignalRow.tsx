import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { ARTICLE_SOURCE_LABELS } from "../api/types";
import type { Signal, SignalStatus } from "../api/types";
import { STATUS_TRANSITION_VALUES } from "../constants/signalStatus";
import FavoriteButton from "./FavoriteButton";

interface SignalRowProps {
  signal: Signal;
  onFavoriteToggle: (signal: Signal) => void;
  selection?: { checked: boolean; onToggle: () => void };
  onTransition?: (id: string, status: SignalStatus) => void;
}

export default function SignalRow({ signal, onFavoriteToggle, selection, onTransition }: SignalRowProps) {
  const { t } = useTranslation("signals");

  return (
    <li>
      <div className="signal-row">
        {selection && (
          <input
            type="checkbox"
            className="signal-checkbox"
            checked={selection.checked}
            onChange={selection.onToggle}
            aria-label={t("select", { title: signal.article_title })}
          />
        )}
        <FavoriteButton isFavorited={signal.is_favorited} onToggle={() => onFavoriteToggle(signal)} />
        <Link to={`/signals/${signal.id}`} className="signal-row-link">
          <div className="signal-row-main">
            <span className={`status-badge status-${signal.status}`}>{t(`status.${signal.status}`)}</span>
            {signal.relevance_score !== null && (
              <span className={`score-badge score-${signal.relevance_score}`}>
                {signal.relevance_score}/5
              </span>
            )}
            <span className="source-badge">{ARTICLE_SOURCE_LABELS[signal.article_source]}</span>
            {signal.open_todo_count > 0 && (
              <span className="todo-pill">{t("openTasks", { count: signal.open_todo_count })}</span>
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
            {STATUS_TRANSITION_VALUES.filter((status) => status !== signal.status).map((status) => (
              <button
                type="button"
                key={status}
                className="secondary"
                onClick={() => onTransition(signal.id, status)}
              >
                {t(`transitions.${status}`)}
              </button>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}
