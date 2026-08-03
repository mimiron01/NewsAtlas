import { useTranslation } from "react-i18next";

import type { ThemeQueryPreview } from "../api/types";

const LOW_RESULT_THRESHOLD = 2;

interface ThemeQueryPreviewPanelProps {
  loading: boolean;
  result: ThemeQueryPreview | null;
  error: string | null;
  googleNewsDisabled: boolean;
}

/** Renders the live query-preview state from useThemeQueryPreview — see
 * docs/topics-ux-improvements-planning.html §1.3. Never blocks submission; a low/zero
 * result count is shown as a hint, not a validation error, since a legitimately narrow
 * topic is still valid. */
export default function ThemeQueryPreviewPanel({
  loading,
  result,
  error,
  googleNewsDisabled,
}: ThemeQueryPreviewPanelProps) {
  const { t } = useTranslation("themes");

  if (googleNewsDisabled) {
    return <p className="field-hint">{t("preview.disabled")}</p>;
  }
  if (loading) {
    return <p className="field-hint">{t("preview.loading")}</p>;
  }
  if (error) {
    return <p className="field-hint">{t("preview.failed")}</p>;
  }
  if (!result) {
    return null;
  }

  return (
    <div className="theme-query-preview">
      <p className="field-hint">
        {t("preview.count", { count: result.article_count })}
        {result.article_count < LOW_RESULT_THRESHOLD && ` — ${t("preview.empty")}`}
      </p>
      {result.sample_headlines.length > 0 && (
        <ul className="theme-query-preview-headlines">
          {result.sample_headlines.map((headline) => (
            <li key={headline}>{headline}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
