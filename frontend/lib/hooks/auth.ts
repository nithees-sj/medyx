"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import type { AuthConfig, Me } from "@/lib/types";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await api.get<Me>("/auth/me");
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    staleTime: 60_000,
  });
}

export function useAuthConfig() {
  return useQuery({
    queryKey: ["auth-config"],
    queryFn: () => api.get<AuthConfig>("/auth/config"),
    staleTime: Infinity,
  });
}

export function useLogout() {
  const qc = useQueryClient();
  const router = useRouter();
  return useMutation({
    mutationFn: () => api.post("/auth/logout"),
    onSuccess: () => {
      qc.clear();
      router.replace("/login");
    },
  });
}

export function homeFor(me: Me | null | undefined): string {
  if (!me) return "/login";
  if (!me.role) return "/onboarding";
  return { patient: "/app", doctor: "/doctor", admin: "/admin" }[me.role];
}

/** Only allow same-site relative paths as post-login destinations. */
export function safeNext(next: string | null | undefined): string | null {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return null;
  return next;
}
