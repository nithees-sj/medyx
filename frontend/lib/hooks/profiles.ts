"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { Profile } from "@/lib/types";

export function useProfiles() {
  return useQuery({ queryKey: ["profiles"], queryFn: () => api.get<Profile[]>("/profiles") });
}

export function useProfile(id: string) {
  return useQuery({ queryKey: ["profile", id], queryFn: () => api.get<Profile>(`/profiles/${id}`) });
}

export function profileLabel(p: Pick<Profile, "display_name" | "relationship">) {
  const first = p.display_name.split(" ")[0];
  const rel = { self: "Me", parent: "Parent", child: "Child", spouse: "Spouse", other: "Family" }[p.relationship];
  return p.relationship === "self" ? "Me" : `${rel} — ${first}`;
}

const LAST_PROFILE_KEY = "ht:last-profile";

export function rememberProfile(id: string) {
  try {
    localStorage.setItem(LAST_PROFILE_KEY, id);
  } catch {
    /* storage unavailable */
  }
}

export function lastProfile(): string | null {
  try {
    return localStorage.getItem(LAST_PROFILE_KEY);
  } catch {
    return null;
  }
}
