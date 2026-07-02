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
