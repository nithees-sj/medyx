"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type {
  Analyte,
  DocumentRow,
  MedicationRow,
  OrgColors,
  ReviewItem,
  TimelineData,
} from "@/lib/record-types";

export const recordKeys = {
  all: (id: string) => ["record", id] as const,
  timeline: (id: string) => ["record", id, "timeline"] as const,
  trends: (id: string) => ["record", id, "trends"] as const,
  meds: (id: string) => ["record", id, "medications"] as const,
  docs: (id: string) => ["record", id, "documents"] as const,
  orgs: (id: string) => ["record", id, "orgs"] as const,
  review: (id: string) => ["record", id, "review"] as const,
};

export function useTimeline(id: string) {
  return useQuery({ queryKey: recordKeys.timeline(id), queryFn: () => api.get<TimelineData>(`/profiles/${id}/timeline`) });
}

export function useTrends(id: string) {
  return useQuery({
    queryKey: recordKeys.trends(id),
    queryFn: () => api.get<{ analytes: Analyte[]; org_colors: OrgColors }>(`/profiles/${id}/trends`),
  });
}

export function useMedications(id: string) {
  return useQuery({
    queryKey: recordKeys.meds(id),
    queryFn: () => api.get<{ medications: MedicationRow[]; org_colors: OrgColors }>(`/profiles/${id}/medications`),
  });
}

export function useDocuments(id: string, opts?: { poll?: boolean }) {
  return useQuery({
    queryKey: recordKeys.docs(id),
    queryFn: () => api.get<DocumentRow[]>(`/profiles/${id}/documents`),
    refetchInterval: (q) =>
      opts?.poll || q.state.data?.some((d) => d.status === "queued" || d.status === "processing") ? 2000 : false,
  });
}

export function useOrgColors(id: string) {
  return useQuery({ queryKey: recordKeys.orgs(id), queryFn: () => api.get<OrgColors>(`/profiles/${id}/orgs`) });
}

export function useReviewQueue(id: string, enabled = true) {
  return useQuery({
    queryKey: recordKeys.review(id),
    queryFn: () => api.get<ReviewItem[]>(`/profiles/${id}/review`),
    enabled,
  });
}

export function orgColor(colors: OrgColors | undefined, org: string | null | undefined): string {
  return (org && colors?.[org]) || "#64748b";
}
