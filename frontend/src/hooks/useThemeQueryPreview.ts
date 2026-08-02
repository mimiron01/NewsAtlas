import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import type { ThemeQueryPreview } from "../api/types";

const DEBOUNCE_MS = 600;

interface PreviewParams {
  queryTerms: string[];
  excludeTerms: string[];
  sourceAllowlist: string[];
  country: string;
  language: string;
  /** Skip calling the endpoint entirely — used when Google News RSS is disabled
   * workspace-wide, so this doesn't fire a request that can only ever 400. */
  disabled: boolean;
}

interface PreviewState {
  loading: boolean;
  result: ThemeQueryPreview | null;
  error: string | null;
}

/** Debounced live preview against POST /theme-watches/preview — see
 * docs/topics-ux-improvements-planning.html §1.3. Shared by the create/edit forms on
 * ThemesPage and the template gallery, so query tuning gets the same instant feedback
 * loop everywhere a topic's terms can be edited. */
export function useThemeQueryPreview({
  queryTerms,
  excludeTerms,
  sourceAllowlist,
  country,
  language,
  disabled,
}: PreviewParams): PreviewState {
  const [state, setState] = useState<PreviewState>({ loading: false, result: null, error: null });
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (disabled || queryTerms.length === 0) {
      setState({ loading: false, result: null, error: null });
      return;
    }
    const requestId = ++requestIdRef.current;
    const timer = window.setTimeout(() => {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      api
        .post<ThemeQueryPreview>("/theme-watches/preview", {
          query_terms: queryTerms,
          exclude_terms: excludeTerms,
          google_news_source_allowlist: sourceAllowlist,
          google_news_country: country || null,
          google_news_language: language || null,
        })
        .then((result) => {
          if (requestIdRef.current === requestId) {
            setState({ loading: false, result, error: null });
          }
        })
        .catch((err) => {
          if (requestIdRef.current === requestId) {
            setState({
              loading: false,
              result: null,
              error: err instanceof ApiError ? err.message : "preview failed",
            });
          }
        });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    JSON.stringify(queryTerms),
    JSON.stringify(excludeTerms),
    JSON.stringify(sourceAllowlist),
    country,
    language,
    disabled,
  ]);

  return state;
}
