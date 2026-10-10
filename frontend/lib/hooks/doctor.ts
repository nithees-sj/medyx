"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Profile } from "@/lib/types";

export interface DoctorPatientRow {
  profile_id: string;
  name: string;
  age: number;
  sex: string;
  blood_group: string;
  healththread_id: string;
  scopes: string[];
  can_write: boolean;
  expires_at: string | null;
  critical_alerts: number;
  warning_alerts: number;
  alert_titles: string[];
  last_activity: string | null;
  documents: number;
  egfr: { date: string; value: number }[];
}

export interface ProfileWithAccess extends Profile {
  access: { is_owner: boolean; scopes: string[]; can_write: boolean; expires_at: string | null } | null;
}

export function useDoctorPatients(enabled = true) {
  return useQuery({
    queryKey: ["doctor-patients"],
    queryFn: () => api.get<DoctorPatientRow[]>("/doctor/patients"),
    enabled,
    refetchInterval: 20_000,
  });
}

export function useWorkspaceProfile(id: string) {
  return useQuery({ queryKey: ["profile", id], queryFn: () => api.get<ProfileWithAccess>(`/profiles/${id}`), retry: false });
}

export interface Citation {
  key: string;
  label?: string;
  document_id?: string;
  doc_label?: string;
  page?: number;
  snippet?: string | null;
  org?: string | null;
  unknown?: boolean;
}

export interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  created_at: string;
  pending?: boolean;
  error?: string;
}

export function useChatHistory(profileId: string) {
  return useQuery({ queryKey: ["chat", profileId], queryFn: () => api.get<ChatMsg[]>(`/profiles/${profileId}/chat`) });
}
