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
    newsdata_enabled: settings.newsdata_enabled,
    newsdata_full_content_enabled: settings.newsdata_full_content_enabled,
    newsdata_use_native_dedupe: settings.newsdata_use_native_dedupe,
    newsdata_backfill_days: settings.newsdata_backfill_days,
    newsdata_max_requests_per_day: settings.newsdata_max_requests_per_day,
    newsdata_max_requests_per_minute: settings.newsdata_max_requests_per_minute,
  };
}
