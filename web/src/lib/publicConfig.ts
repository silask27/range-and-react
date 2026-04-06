"use client";

import { API_BASE } from "./api";

export type PublicConfig = {
  app_name: string;
  environment: string;
  version: string;
  support_email: string;
  legal?: {
    privacy_path?: string;
    terms_path?: string;
    status_path?: string;
    company_name?: string;
    effective_date?: string;
    jurisdiction?: string;
    support_email?: string;
  };
  ops?: {
    public_status_detailed_checks?: boolean;
    public_status_show_demo_details?: boolean;
  };
  demo?: {
    enabled?: boolean;
    public_credentials?: boolean;
    organization_name?: string;
    seed_command?: string | null;
    accounts?: Array<{ label: string; email: string; role: string; password?: string }>;
  };
};

let cachedPromise: Promise<PublicConfig | null> | null = null;

export async function fetchPublicConfig(): Promise<PublicConfig | null> {
  if (!cachedPromise) {
    cachedPromise = fetch(`${API_BASE}/platform/public-config`, { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) return null;
        return (await res.json()) as PublicConfig;
      })
      .catch(() => null);
  }
  return cachedPromise;
}
