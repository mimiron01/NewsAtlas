export type UserRole = "admin" | "user";

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
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

  newsdata_enabled: boolean;
  newsdata_api_key_configured: boolean;
  newsdata_api_key_source: MistralApiKeySource;
  newsdata_api_key_last4: string | null;
  newsdata_full_content_enabled: boolean;
  newsdata_use_native_dedupe: boolean;
  newsdata_backfill_days: number;
  newsdata_max_requests_per_day: number;
  newsdata_max_requests_per_minute: number;
}

export interface WorkspaceSettingsUpdatePayload {
  company_name: string;
  offering_description: string;
  digest_send_time: string;
  ingestion_interval_hours: number;
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

  newsdata_enabled: boolean;
  // Omit to leave the current key unchanged; "" clears the in-app override.
  newsdata_api_key?: string;
  newsdata_full_content_enabled: boolean;
  newsdata_use_native_dedupe: boolean;
  newsdata_backfill_days: number;
  newsdata_max_requests_per_day: number;
  newsdata_max_requests_per_minute: number;
}

export type ArticleSource = "newsapi" | "google_news_rss" | "newsdata";

export const ARTICLE_SOURCE_LABELS: Record<ArticleSource, string> = {
  newsapi: "NewsAPI.org",
  google_news_rss: "Google News",
  newsdata: "NewsData.io",
};

export interface NewsSourceUsageEntry {
  call_type: string;
  target_company_name: string | null;
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

export interface TargetCompany {
  id: string;
  name: string;
  keywords: string[];
  industry: string | null;
  is_active: boolean;
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
}

export interface IngestionRunResult {
  target_companies_processed: number;
  articles_fetched: number;
  articles_new: number;
  signals_created: number;
  duplicates_skipped: number;
  triaged_out: number;
  by_source: Record<string, number>;
  rate_limited: Record<string, number>;
  errors: string[];
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
