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

export interface WorkspaceSettings {
  id: string;
  company_name: string;
  offering_description: string;
  digest_send_time: string;
  ingestion_interval_hours: number;
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

export interface Signal {
  id: string;
  status: SignalStatus;
  summary: string;
  business_relevance: string;
  outreach_snippet: string;
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
  errors: string[];
}
