import type { WorkspaceSettings, WorkspaceSettingsUpdatePayload } from "../../api/types";

// The PUT /settings endpoint replaces the whole settings row, so every tab that edits a
// slice of it (company info, sources, AI config) still has to resend the fields owned by
// the other tabs unchanged.
export function buildSettingsPayload(settings: WorkspaceSettings): WorkspaceSettingsUpdatePayload {
  return {
    company_name: settings.company_name,
    offering_description: settings.offering_description,
    digest_send_time: settings.digest_send_time,
    ingestion_interval_hours: settings.ingestion_interval_hours,
    max_articles_per_company_per_run: settings.max_articles_per_company_per_run,
    main_language: settings.main_language,
    mistral_model: settings.mistral_model,
    mistral_triage_model: settings.mistral_triage_model,
    mistral_embed_model: settings.mistral_embed_model,
    mistral_triage_enabled: settings.mistral_triage_enabled,
    mistral_dedupe_similarity_threshold: settings.mistral_dedupe_similarity_threshold,
    newsapi_enabled: settings.newsapi_enabled,
    newsapi_max_requests_per_day: settings.newsapi_max_requests_per_day,
    google_news_rss_enabled: settings.google_news_rss_enabled,
    google_news_rss_country: settings.google_news_rss_country,
    google_news_rss_language: settings.google_news_rss_language,
    google_news_rss_max_requests_per_minute: settings.google_news_rss_max_requests_per_minute,
    google_news_source_allowlist: settings.google_news_source_allowlist,
    google_news_source_denylist: settings.google_news_source_denylist,
    google_news_time_operator_enabled: settings.google_news_time_operator_enabled,
    google_news_query_strategy: settings.google_news_query_strategy,
    google_news_resolve_urls_enabled: settings.google_news_resolve_urls_enabled,
    google_news_fetch_snippets_enabled: settings.google_news_fetch_snippets_enabled,
    max_enrichment_fetches_per_run: settings.max_enrichment_fetches_per_run,
    max_enrichment_seconds_per_run: settings.max_enrichment_seconds_per_run,
    theme_news_sources: settings.theme_news_sources,
    max_theme_requests_per_run_per_source: settings.max_theme_requests_per_run_per_source,
    newsdata_enabled: settings.newsdata_enabled,
    newsdata_full_content_enabled: settings.newsdata_full_content_enabled,
    newsdata_use_native_dedupe: settings.newsdata_use_native_dedupe,
    newsdata_backfill_days: settings.newsdata_backfill_days,
    newsdata_max_requests_per_day: settings.newsdata_max_requests_per_day,
    newsdata_max_requests_per_minute: settings.newsdata_max_requests_per_minute,
    max_articles_per_theme_per_run: settings.max_articles_per_theme_per_run,
    max_active_theme_watches: settings.max_active_theme_watches,
  };
}
