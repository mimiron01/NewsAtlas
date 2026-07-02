export interface User {
  id: string;
  email: string;
  name: string;
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
