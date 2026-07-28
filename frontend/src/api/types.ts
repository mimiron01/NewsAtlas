export type UserRole = "admin" | "user";
export type SupportedLanguage = "en" | "de";

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  // null = no personal override, follow workspace_main_language.
  preferred_language: SupportedLanguage | null;
  workspace_main_language: SupportedLanguage;
}

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  created_at: string;
}

export interface CompanyFollower {
  user_id: string;
  email: string;
  name: string;
  is_muted: boolean;
  assigned_by: string | null;
  created_at: string;
}

export type MistralApiKeySource = "workspace" | "environment" | "unset";

export interface WorkspaceSettings {
  id: string;
  company_name: string;
  offering_description: string;
  digest_send_time: string;
  ingestion_interval_hours: number;
  max_articles_per_company_per_run: number;
  main_language: SupportedLanguage;
  mistral_model: string;
  mistral_triage_model: string;
  mistral_embed_model: string;
  mistral_triage_enabled: boolean;
  mistral_dedupe_similarity_threshold: number;
  mistral_api_key_configured: boolean;
  mistral_api_key_source: MistralApiKeySource;
  mistral_api_key_last4: string | null;

  newsapi_enabled: boolean;
  newsapi_max_requests_per_day: number;

  google_news_rss_enabled: boolean;
  google_news_rss_country: string;
  google_news_rss_language: string;
  google_news_rss_max_requests_per_minute: number;
  google_news_source_allowlist: string[];

  newsdata_enabled: boolean;
  newsdata_api_key_configured: boolean;
  newsdata_api_key_source: MistralApiKeySource;
  newsdata_api_key_last4: string | null;
  newsdata_full_content_enabled: boolean;
  newsdata_use_native_dedupe: boolean;
  newsdata_backfill_days: number;
  newsdata_max_requests_per_day: number;
  newsdata_max_requests_per_minute: number;

  max_articles_per_theme_per_run: number;
  max_active_theme_watches: number;
}

export interface WorkspaceSettingsUpdatePayload {
  company_name: string;
  offering_description: string;
  digest_send_time: string;
  ingestion_interval_hours: number;
  max_articles_per_company_per_run: number;
  main_language: SupportedLanguage;
  mistral_model: string;
  mistral_triage_model: string;
  mistral_embed_model: string;
  mistral_triage_enabled: boolean;
  mistral_dedupe_similarity_threshold: number;
  // Omit to leave the current key unchanged; "" clears the in-app override.
  mistral_api_key?: string;

  newsapi_enabled: boolean;
  newsapi_max_requests_per_day: number;

  google_news_rss_enabled: boolean;
  google_news_rss_country: string;
  google_news_rss_language: string;
  google_news_rss_max_requests_per_minute: number;
  google_news_source_allowlist: string[];

  newsdata_enabled: boolean;
  // Omit to leave the current key unchanged; "" clears the in-app override.
  newsdata_api_key?: string;
  newsdata_full_content_enabled: boolean;
  newsdata_use_native_dedupe: boolean;
  newsdata_backfill_days: number;
  newsdata_max_requests_per_day: number;
  newsdata_max_requests_per_minute: number;

  max_articles_per_theme_per_run: number;
  max_active_theme_watches: number;
}

export type ArticleSource = "newsapi" | "google_news_rss" | "newsdata";

export const ARTICLE_SOURCE_LABELS: Record<ArticleSource, string> = {
  newsapi: "NewsAPI.org",
  google_news_rss: "Google News",
  newsdata: "NewsData.io",
};

export interface NewsSourceUsageEntry {
  call_type: string;
  // Mutually exclusive: a call is made on behalf of one company or one topic. Both null
  // for a historical row logged before topic attribution existed.
  target_company_name: string | null;
  theme_watch_name: string | null;
  requests_used: number;
  articles_returned: number;
  created_at: string;
}

export interface NewsSourceUsageStat {
  source: ArticleSource;
  enabled: boolean;
  requests_last_minute: number;
  requests_per_minute_limit: number | null;
  requests_today: number;
  requests_per_day_limit: number | null;
  rate_limited_last_24h: number;
  recent: NewsSourceUsageEntry[];
}

export interface NewsUsageSummary {
  sources: NewsSourceUsageStat[];
}

export interface BackfillTriggerResult {
  scheduled: boolean;
  message: string;
  target_company_id: string;
}

export interface TargetCompanyImportSkipped {
  row: number;
  name: string;
  reason: string;
}

export interface TargetCompanyImportError {
  row: number;
  reason: string;
}

export interface TargetCompanyImportResult {
  created: TargetCompany[];
  skipped: TargetCompanyImportSkipped[];
  errors: TargetCompanyImportError[];
}

export interface TargetCompanyBulkDeleteResult {
  deleted: number;
  not_found: number;
}

export interface TargetCompany {
  id: string;
  name: string;
  keywords: string[];
  industry: string | null;
  is_active: boolean;
  google_news_source_allowlist: string[];
  created_by: string | null;
  is_muted: boolean | null;
  follower_count: number;
  backfilled_at: string | null;
}

export type SignalStatus = "new" | "reviewed" | "archived" | "dismissed";

export type SignalType =
  | "funding"
  | "leadership_change"
  | "expansion"
  | "hiring_surge"
  | "layoffs"
  | "product_launch"
  | "partnership"
  | "competitor_mention"
  | "other";

export type SignalConfidence = "low" | "medium" | "high";

export interface SignalEntities {
  amount?: string;
  people?: string[];
  tags?: string[];
}

export interface Signal {
  id: string;
  status: SignalStatus;
  summary: string;
  business_relevance: string;
  supporting_quote: string;
  outreach_snippet_email: string;
  outreach_snippet_linkedin: string;
  outreach_call_opener: string;
  relevance_score: number | null;
  signal_type: SignalType | null;
  confidence: SignalConfidence | null;
  entities: SignalEntities | null;
  created_at: string;
  article_id: string;
  article_title: string;
  article_url: string;
  article_source_name: string;
  article_published_at: string | null;
  article_source: ArticleSource;
  article_external_sentiment: string | null;
  article_external_tags: string[] | null;
  // True when the article came from a source (Google News RSS) whose description field
  // is never real content, only a repeat of the title — surfaced as a "Limited detail" badge.
  headline_only: boolean;
  target_company_id: string;
  target_company_name: string;
  is_favorited: boolean;
  open_todo_count: number;
}

export interface SignalTodo {
  id: string;
  signal_id: string;
  text: string;
  is_done: boolean;
  completed_at: string | null;
  created_at: string;
}

export interface SignalTodoWithContext extends SignalTodo {
  article_title: string;
  target_company_name: string;
}

export interface DashboardSummary {
  top_signals: Signal[];
  new_signal_count: number;
  favorite_count: number;
  recent_favorites: Signal[];
  open_todo_count: number;
  open_todos: SignalTodoWithContext[];
  dismissed_signal_count: number;
  // Always 0 for non-admins — the underlying skipped-articles queue is admin-only.
  skipped_article_count: number;
  // Theme-watch equivalents of new_signal_count/top_signals, follow-scoped and
  // mute-respecting the same way. 0/[] for a user who follows no topics.
  new_theme_match_count: number;
  top_theme_matches: ThemeMatch[];
}

export type IngestionRunStatusValue = "running" | "completed" | "failed" | "cancelled";
export type IngestionTrigger = "manual" | "scheduled";
export type IngestionStep = "fetching" | "summarizing" | "waiting";

export interface IngestionRunStatus {
  id: string;
  status: IngestionRunStatusValue;
  // True once an admin has requested cancellation but the pipeline hasn't yet reached
  // its next checkpoint — status is still "running" in this window.
  cancel_requested: boolean;
  trigger: IngestionTrigger;
  // Set only for a single-topic run started from the Themes page; null for an ordinary
  // full run over every company and topic.
  theme_watch_id: string | null;
  started_at: string;
  finished_at: string | null;
  progress_percent: number;

  current_step: IngestionStep | null;
  current_company_name: string | null;
  current_theme_name: string | null;
  companies_total: number;
  companies_processed: number;
  // Shared by both phases: while themes are being processed these count that theme's
  // matches, not a company's articles.
  articles_total_this_company: number;
  articles_processed_this_company: number;

  articles_fetched: number;
  articles_new: number;
  signals_created: number;
  duplicates_skipped: number;
  triaged_out: number;
  by_source: Record<string, number>;
  rate_limited: Record<string, number>;
  errors: string[];
  fatal_error: string | null;

  // themes_total/themes_processed are live, like the company counters above;
  // theme_matches_created settles once the run finishes.
  themes_total: number;
  themes_processed: number;
  theme_matches_created: number;
}

/** Non-sensitive workspace capability flags, readable by any authenticated user
 *  (GET /settings/public) — the admin-only WorkspaceSettings is a superset. */
export interface PublicWorkspaceSettings {
  google_news_rss_enabled: boolean;
  google_news_rss_country: string;
  google_news_rss_language: string;
  manual_trigger_cooldown_seconds: number;
}

export interface SkippedArticle {
  id: string;
  title: string;
  url: string;
  source_name: string;
  source: ArticleSource;
  published_at: string | null;
  fetched_at: string;
  skip_reason: string;
  triage_reason: string | null;
  headline_only: boolean;
  target_company_id: string;
  target_company_name: string;
}

export interface AIUsageByCallType {
  call_type: string;
  call_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface AIUsageByTargetCompany {
  target_company_id: string | null;
  target_company_name: string | null;
  total_tokens: number;
}

export interface AIUsageSummary {
  period_days: number;
  total_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  by_call_type: AIUsageByCallType[];
  by_target_company: AIUsageByTargetCompany[];
}

export interface ThemeWatch {
  id: string;
  name: string;
  query_terms: string[];
  industry: string | null;
  is_active: boolean;
  google_news_source_allowlist: string[];
  // null = inherit the workspace-wide Google News edition. A topic about a national
  // market ("Startups DE") needs its own edition, since the workspace default can only
  // ever match one market.
  google_news_country: string | null;
  google_news_language: string | null;
  // Drives the per-topic fetch button's cooldown countdown.
  last_manual_run_at: string | null;
  created_by: string | null;
  // Per-follow fields: null when the requester (an admin using ?scope=all) doesn't
  // themselves follow this theme.
  is_muted: boolean | null;
  follower_count: number;
}

export interface ThemeFollower {
  user_id: string;
  email: string;
  name: string;
  is_muted: boolean;
  assigned_by: string | null;
  created_at: string;
}

export interface ThemeMatch {
  id: string;
  status: SignalStatus;
  summary: string | null;
  business_relevance: string | null;
  supporting_quote: string | null;
  relevance_score: number | null;
  signal_type: SignalType | null;
  confidence: SignalConfidence | null;
  entities: SignalEntities | null;
  fetched_at: string;
  title: string;
  url: string;
  source_name: string;
  published_at: string | null;
  source: ArticleSource;
  headline_only: boolean;
  theme_watch_id: string;
  theme_watch_name: string;
  // What the AI extraction pass identified, if anything. matched_target_company_id/name
  // are set once that name auto-resolves to an existing TargetCompany; "Track this
  // company" is only offered when extracted_company_name is set but
  // matched_target_company_id isn't (see docs/theme-search-planning.html §4.3).
  extracted_company_name: string | null;
  matched_target_company_id: string | null;
  matched_target_company_name: string | null;
}
