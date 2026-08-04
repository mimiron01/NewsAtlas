import { useTranslation } from "react-i18next";

import { ARTICLE_SOURCE_LABELS } from "../api/types";
import type { ArticleSource } from "../api/types";
import HelpTooltip from "./HelpTooltip";

const SOURCES: ArticleSource[] = ["google_news_rss", "newsapi", "newsdata"];

/**
 * Which news sources a topic may use, with the same inherit-or-override shape as the
 * trusted-sources field.
 *
 * Topics were limited to Google News until multi-provider support landed, and that is
 * still the default — so "inherit" is the normal state and overriding is the exception,
 * which the control's default selection reflects.
 */
export default function ThemeSourceSelector({
  value,
  onChange,
}: {
  value: string[] | null;
  onChange: (value: string[] | null) => void;
}) {
  const { t } = useTranslation("themes");

  return (
    <div className="source-allowlist-field">
      <span className="field-label">
        {t("addTheme.newsSources")} <HelpTooltip content={t("addTheme.newsSourcesHint")} />
      </span>
      <div className="field-row">
        <label className="checkbox-label">
          <input type="radio" checked={value === null} onChange={() => onChange(null)} />
          {t("addTheme.newsSourcesInherit")}
        </label>
        <label className="checkbox-label">
          <input
            type="radio"
            checked={value !== null}
            onChange={() => onChange(value ?? ["google_news_rss"])}
          />
          {t("addTheme.newsSourcesCustom")}
        </label>
      </div>
      {value !== null && (
        <div className="field-row">
          {SOURCES.map((source) => (
            <label key={source} className="checkbox-label">
              <input
                type="checkbox"
                checked={value.includes(source)}
                onChange={(e) =>
                  onChange(
                    e.target.checked
                      ? [...value, source]
                      : value.filter((selected) => selected !== source)
                  )
                }
              />
              {ARTICLE_SOURCE_LABELS[source]}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
