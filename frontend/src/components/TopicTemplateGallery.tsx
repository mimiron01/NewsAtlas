import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiError } from "../api/client";
import type { SuggestedTopic, ThemeDuplicateNameDetail, ThemeWatch, TopicTemplate } from "../api/types";
import { useToast } from "../context/ToastContext";

interface TopicTemplateGalleryProps {
  onApplied: (theme: ThemeWatch) => void;
  onBack: () => void;
}

interface PendingDuplicate {
  key: string;
  detail: ThemeDuplicateNameDetail;
  retry: () => Promise<void>;
}

/** Template gallery + AI-suggested topics — see
 * docs/topics-ux-improvements-planning.html §2.2/§2.3. Suggestions are grounded in the
 * same template library shown above them; each suggestion's card shows "based on: X"
 * when the AI adapted an existing template rather than writing one from scratch. */
export default function TopicTemplateGallery({ onApplied, onBack }: TopicTemplateGalleryProps) {
  const { t } = useTranslation("themes");
  const { showToast } = useToast();

  const [templates, setTemplates] = useState<TopicTemplate[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(true);
  const [templatesError, setTemplatesError] = useState<string | null>(null);

  const [suggestions, setSuggestions] = useState<SuggestedTopic[] | null>(null);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [suggestionsError, setSuggestionsError] = useState(false);

  const [applyingKey, setApplyingKey] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<PendingDuplicate | null>(null);

  useEffect(() => {
    api
      .get<TopicTemplate[]>("/topic-templates")
      .then((result) => {
        setTemplates(result);
        setTemplatesError(null);
      })
      .catch(() => setTemplatesError(t("templates.loadFailed")))
      .finally(() => setTemplatesLoading(false));
  }, [t]);

  function loadSuggestions() {
    setSuggestionsLoading(true);
    setSuggestionsError(false);
    api
      .get<SuggestedTopic[]>("/theme-watches/suggestions")
      .then(setSuggestions)
      .catch(() => setSuggestionsError(true))
      .finally(() => setSuggestionsLoading(false));
  }

  useEffect(loadSuggestions, []);

  async function applyTemplate(
    key: string,
    templateId: string,
    overrides: { name?: string; query_terms?: string[]; exclude_terms?: string[] },
    confirmMerge = false
  ) {
    setApplyingKey(key);
    try {
      const theme = await api.post<ThemeWatch>(`/topic-templates/${templateId}/apply`, {
        ...overrides,
        confirm_merge: confirmMerge,
      });
      setDuplicate(null);
      onApplied(theme);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const detail = err.detail as ThemeDuplicateNameDetail | undefined;
        if (detail?.code === "duplicate_name") {
          setDuplicate({
            key,
            detail,
            retry: () => applyTemplate(key, templateId, overrides, true),
          });
          return;
        }
      }
      showToast(err instanceof ApiError ? err.message : t("templates.applyFailed"), "error");
    } finally {
      setApplyingKey(null);
    }
  }

  async function applyFreeformSuggestion(key: string, suggestion: SuggestedTopic, confirmMerge = false) {
    setApplyingKey(key);
    try {
      const theme = await api.post<ThemeWatch>("/theme-watches", {
        name: suggestion.name,
        query_terms: suggestion.query_terms,
        exclude_terms: suggestion.exclude_terms,
        confirm_merge: confirmMerge,
      });
      setDuplicate(null);
      onApplied(theme);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const detail = err.detail as ThemeDuplicateNameDetail | undefined;
        if (detail?.code === "duplicate_name") {
          setDuplicate({
            key,
            detail,
            retry: () => applyFreeformSuggestion(key, suggestion, true),
          });
          return;
        }
      }
      showToast(err instanceof ApiError ? err.message : t("templates.applyFailed"), "error");
    } finally {
      setApplyingKey(null);
    }
  }

  function applySuggestion(suggestion: SuggestedTopic) {
    const key = `suggestion:${suggestion.name}`;
    if (suggestion.based_on_template_id) {
      applyTemplate(key, suggestion.based_on_template_id, {
        name: suggestion.name,
        query_terms: suggestion.query_terms,
        exclude_terms: suggestion.exclude_terms,
      });
    } else {
      applyFreeformSuggestion(key, suggestion);
    }
  }

  const categories = Array.from(new Set(templates.map((tpl) => tpl.category || t("templates.title"))));

  return (
    <div className="panel-card">
      <div className="feed-toolbar">
        <div>
          <h2>{t("templates.title")}</h2>
          <p className="subtitle">{t("templates.subtitle")}</p>
        </div>
        <button type="button" className="secondary" onClick={onBack}>
          {t("templates.backToList")}
        </button>
      </div>

      <div className="template-suggestions">
        <div className="feed-toolbar">
          <div>
            <h3>{t("templates.suggestedTitle")}</h3>
            <p className="subtitle">{t("templates.suggestedSubtitle")}</p>
          </div>
          <button type="button" className="secondary" onClick={loadSuggestions} disabled={suggestionsLoading}>
            {t("templates.suggestedRefresh")}
          </button>
        </div>
        {suggestionsLoading && <p className="subtitle">{t("preview.loading")}</p>}
        {!suggestionsLoading && suggestionsError && (
          <p className="error-text">{t("templates.suggestedFailed")}</p>
        )}
        {!suggestionsLoading && !suggestionsError && suggestions !== null && suggestions.length === 0 && (
          <p className="subtitle">{t("templates.suggestedEmpty")}</p>
        )}
        {!suggestionsLoading && suggestions !== null && suggestions.length > 0 && (
          <div className="template-card-grid">
            {suggestions.map((suggestion) => {
              const key = `suggestion:${suggestion.name}`;
              return (
                <div className="template-card" key={key}>
                  <strong>{suggestion.name}</strong>
                  <p className="subtitle">{suggestion.rationale}</p>
                  {suggestion.based_on_template_name && (
                    <p className="field-hint">
                      {t("templates.basedOn", { name: suggestion.based_on_template_name })}
                    </p>
                  )}
                  <div className="keywords">{suggestion.query_terms.join(", ")}</div>
                  {suggestion.exclude_terms.length > 0 && (
                    <p className="field-hint">
                      {t("templates.excludes", { terms: suggestion.exclude_terms.join(", ") })}
                    </p>
                  )}
                  {duplicate?.key === key && (
                    <div className="panel-card warning-banner">
                      <p className="subtitle">
                        {t("duplicate.body", {
                          name: suggestion.name,
                          terms: duplicate.detail.existing_query_terms.join(", "),
                        })}
                      </p>
                      <div className="actions">
                        <button type="button" onClick={() => duplicate.retry()}>
                          {t("duplicate.followExisting")}
                        </button>
                        <button type="button" onClick={() => setDuplicate(null)}>
                          {t("duplicate.useDifferentName")}
                        </button>
                      </div>
                    </div>
                  )}
                  <button
                    type="button"
                    disabled={applyingKey === key}
                    onClick={() => applySuggestion(suggestion)}
                  >
                    {t("templates.useTemplate")}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {templatesLoading && <p className="subtitle">{t("preview.loading")}</p>}
      {templatesError && <p className="error-text">{templatesError}</p>}

      {!templatesLoading &&
        !templatesError &&
        categories.map((category) => (
          <div key={category} className="template-category">
            <h3>{category}</h3>
            <div className="template-card-grid">
              {templates
                .filter((tpl) => (tpl.category || t("templates.title")) === category)
                .map((tpl) => {
                  const key = `template:${tpl.id}`;
                  return (
                    <div className="template-card" key={key}>
                      <strong>{tpl.name}</strong>
                      <p className="subtitle">{tpl.description}</p>
                      <div className="keywords">{tpl.query_terms.join(", ")}</div>
                      {tpl.exclude_terms.length > 0 && (
                        <p className="field-hint">
                          {t("templates.excludes", { terms: tpl.exclude_terms.join(", ") })}
                        </p>
                      )}
                      {duplicate?.key === key && (
                        <div className="panel-card warning-banner">
                          <p className="subtitle">
                            {t("duplicate.body", {
                              name: tpl.name,
                              terms: duplicate.detail.existing_query_terms.join(", "),
                            })}
                          </p>
                          <div className="actions">
                            <button type="button" onClick={() => duplicate.retry()}>
                              {t("duplicate.followExisting")}
                            </button>
                            <button type="button" onClick={() => setDuplicate(null)}>
                              {t("duplicate.useDifferentName")}
                            </button>
                          </div>
                        </div>
                      )}
                      <button
                        type="button"
                        disabled={applyingKey === key}
                        onClick={() => applyTemplate(key, tpl.id, {})}
                      >
                        {t("templates.useTemplate")}
                      </button>
                    </div>
                  );
                })}
            </div>
          </div>
        ))}
    </div>
  );
}
