"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export interface CheckRow {
  kind: "format" | "duplicate" | "registry" | "identity" | "document";
  status: "passed" | "warning" | "failed" | "missing" | "not_configured" | "error";
  summary: string;
  provider: string | null;
  details: Record<string, unknown>;
}

export interface DoctorRow {
  user_id: string;
  email: string;
  full_name: string;
  specialty: string;
  organization: string;
  council: string;
  registration_number: string;
  verification_status: "pending" | "verified" | "rejected" | "suspended";
  verification_method: string | null;
  review_note: string | null;
  created_at: string;
  verified_at: string | null;
  last_checked_at: string | null;
  next_check_at: string | null;
  decision: "approve" | "reject" | "review" | null;
  risk: "low" | "medium" | "high" | null;
  reasons: string[];
  checks: CheckRow[];
  certificate: { filename: string; mime: string; uploaded_at: string; reading: boolean } | null;
}

export interface VerificationConfig {
  registry: { configured: boolean; provider: string | null; url_host: string | null };
  auto_approve: boolean;
  auto_reject: boolean;
  recheck_days: number;
  recheck_job: { last_run: string | null; ok: boolean | null; result: string | null; error: string | null } | null;
}

export interface Overview {
  kpis: {
    users: number;
    users_by_role: Record<string, number>;
    doctors: Record<string, number>;
    profiles: number;
    documents: number;
    documents_by_status: Record<string, number>;
    active_consents: number;
    active_alerts: number;
    critical_alerts: number;
    alerts_by_type: Record<string, number>;
  };
  last_24h: Record<
    | "sign_ins"
    | "failed_sign_ins"
    | "active_users"
    | "uploads"
    | "doctor_record_access"
    | "requests"
    | "server_errors"
    | "access_denied"
    | "ai_calls"
    | "ai_failures"
    | "emergency_views"
    | "critical_overrides",
    number
  >;
  attention: { kind: string; severity: "critical" | "warning" | "info"; title: string; count: number; link: string }[];
  daily: { date: string; sign_ins: number; uploads: number; doctor_access: number; ai_calls: number }[];
}

export interface ActivityItem {
  id: string;
  at: string;
  source: "record" | "system";
  category: string;
  kind: string;
  severity: "info" | "warning" | "error";
  actor: string;
  actor_role: string | null;
  target: string | null;
  summary: string;
  ip: string | null;
}

export interface RequestMetrics {
  hours: number;
  totals: { requests: number; client_errors: number; server_errors: number; p50_ms: number; p95_ms: number };
  series: { at: string; requests: number; client_errors: number; server_errors: number }[];
  routes: {
    method: string;
    route: string;
    requests: number;
    client_errors: number;
    server_errors: number;
    p50_ms: number;
    p95_ms: number;
    max_ms: number;
  }[];
  recent_errors: { at: string; method: string; route: string; status: number; error: string | null; role: string | null }[];
}

export interface AIGroup {
  key: string;
  calls: number;
  failures: number;
  rate_limited: number;
  avg_ms: number;
  input_tokens: number;
  output_tokens: number;
}

export interface AIMetrics {
  hours: number;
  config: {
    configured: boolean;
    model: string;
    fallback_model: string | null;
    requests_per_minute: number;
    calls_last_minute: number;
  };
  totals: { calls: number; failures: number; rate_limited: number; avg_ms: number; input_tokens: number; output_tokens: number };
  by_purpose: AIGroup[];
  by_model: AIGroup[];
  recent: {
    at: string;
    purpose: string;
    model: string;
    ok: boolean;
    ms: number;
    input_tokens: number | null;
    output_tokens: number | null;
    error: string | null;
  }[];
}

export interface PipelineMetrics {
  by_status: Record<string, number>;
  queue_depth: number;
  workers: number;
  avg_processing_seconds_24h: number;
  in_flight: { label: string; stage: string; status: string; since: string; profile: string }[];
  failed: {
    id: string;
    label: string;
    profile: string;
    stage: string;
    error: string | null;
    uploader_role: string;
    uploaded_at: string;
    failed_at: string;
  }[];
}

export interface SharingMetrics {
  consents_by_status: Record<string, number>;
  active: number;
  expiring_24h: number;
  created_7d: number;
  revoked_7d: number;
  emergency_cards_enabled: number;
  emergency_views_24h: number;
  emergency_views_7d: number;
  invalid_links_24h: number;
  recent_emergency_views: { at: string; profile: string; ip: string | null; user_agent: string }[];
}

export interface SystemHealth {
  started_at: string;
  uptime_seconds: number;
  demo_mode: boolean;
  dependencies: {
    database: { ok: boolean };
    fhir: { ok: boolean; version: string | null; url: string };
    ai: { ok: boolean; model: string; fallback_model: string | null };
    registry: { ok: boolean; configured: boolean; provider: string | null; url_host: string | null };
  };
  ingest_worker: { queue_depth: number; workers_alive: number };
  jobs: {
    name: string;
    runs: number;
    last_run: string | null;
    ok: boolean | null;
    result: string | null;
    error: string | null;
    interval_seconds: number | null;
  }[];
  telemetry_buffer: Record<string, number>;
}

export interface UserRow {
  id: string;
  name: string;
  email: string;
  role: string | null;
  doctor_status: string | null;
  profiles: number;
  created_at: string;
  last_login_at: string | null;
  sign_in: "google" | "demo";
}

const LIVE = 15_000;

export const useOverview = () =>
  useQuery({ queryKey: ["admin", "overview"], queryFn: () => api.get<Overview>("/admin/overview"), refetchInterval: LIVE });
export const useSharing = () =>
  useQuery({ queryKey: ["admin", "sharing"], queryFn: () => api.get<SharingMetrics>("/admin/sharing"), refetchInterval: LIVE });
export const useHealth = () =>
  useQuery({ queryKey: ["admin", "health"], queryFn: () => api.get<SystemHealth>("/admin/health"), refetchInterval: LIVE });
export const usePipeline = () =>
  useQuery({ queryKey: ["admin", "pipeline"], queryFn: () => api.get<PipelineMetrics>("/admin/pipeline"), refetchInterval: 5_000 });
export const useRequestMetrics = (hours: number) =>
  useQuery({
    queryKey: ["admin", "requests", hours],
    queryFn: () => api.get<RequestMetrics>(`/admin/requests?hours=${hours}`),
    refetchInterval: LIVE,
  });
export const useAIMetrics = (hours: number) =>
  useQuery({
    queryKey: ["admin", "ai", hours],
    queryFn: () => api.get<AIMetrics>(`/admin/ai?hours=${hours}`),
    refetchInterval: LIVE,
  });
export const useVerificationConfig = () =>
  useQuery({ queryKey: ["admin", "verification-config"], queryFn: () => api.get<VerificationConfig>("/admin/verification/config") });
export const useDoctors = (status: string) =>
  useQuery({
    queryKey: ["admin", "doctors", status],
    queryFn: () => api.get<DoctorRow[]>(`/admin/doctors?status_filter=${status}`),
    refetchInterval: LIVE,
  });
export const useTrustedDomains = () =>
  useQuery({
    queryKey: ["admin", "trusted-domains"],
    queryFn: () => api.get<{ domain: string; organization: string; created_at: string }[]>("/admin/trusted-domains"),
  });
