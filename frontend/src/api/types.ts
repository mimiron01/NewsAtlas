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
}

export interface TargetCompany {
  id: string;
  name: string;
  keywords: string[];
  industry: string | null;
  is_active: boolean;
  is_muted: boolean | null;
  follower_count: number;
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
  target_company_id: string;
  target_company_name: string;
}

export interface IngestionRunResult {
  target_companies_processed: number;
  articles_fetched: number;
  articles_new: number;
  signals_created: number;
  duplicates_skipped: number;
  triaged_out: number;
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
