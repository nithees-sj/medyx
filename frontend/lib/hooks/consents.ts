"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export type Scope = "conditions" | "medications" | "allergies" | "labs" | "documents" | "notes" | "mental_health";

export const SCOPE_LABEL: Record<Scope, string> = {
  conditions: "Conditions",
  medications: "Medicines",
  allergies: "Allergies",
  labs: "Lab results & vitals",
  documents: "Documents",
  notes: "Clinical notes",
  mental_health: "Mental health",
};

export const SCOPES: Scope[] = ["conditions", "medications", "allergies", "labs", "documents", "notes", "mental_health"];
export const DEFAULT_SCOPES: Scope[] = ["conditions", "medications", "allergies", "labs"];
export const DURATIONS = [
  { hours: 24, label: "24 hours" },
  { hours: 168, label: "7 days" },
  { hours: 720, label: "30 days" },
];

export interface ConsentRow {
  id: string;
  profile_id: string;
  status: "pending_claim" | "requested" | "active" | "revoked" | "expired" | "denied";
  scopes: Scope[];
  can_write: boolean;
  purpose: string | null;
  duration_hours: number;
  expires_at: string | null;
  claim_deadline: string | null;
  created_at: string;
  revoked_at: string | null;
  doctor: { user_id: string; name: string; specialty: string; organization: string; verified: boolean; email: string | null } | null;
}

export interface AuditRow {
  id: string;
  actor: string;
  actor_is_owner: boolean;
  action: string;
  verb: string;
  scopes: string[];
  details: Record<string, unknown>;
  ip: string | null;
  created_at: string;
}

export function useConsents(profileId: string, poll = false) {
  return useQuery({
    queryKey: ["consents", profileId],
    queryFn: () => api.get<ConsentRow[]>(`/profiles/${profileId}/consents`),
    refetchInterval: poll ? 3000 : false,
  });
}

export function useAudit(profileId: string) {
  return useQuery({ queryKey: ["audit", profileId], queryFn: () => api.get<AuditRow[]>(`/profiles/${profileId}/audit`) });
}

export function scopesText(scopes: string[]): string {
  const names = scopes.map((s) => (SCOPE_LABEL[s as Scope] ?? s).toLowerCase());
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}
