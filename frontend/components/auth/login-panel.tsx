"use client";

import { GoogleLogin, GoogleOAuthProvider } from "@react-oauth/google";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, ShieldCheck, Stethoscope, UserRound, UserRoundX } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { toast } from "sonner";

import { Logo } from "@/components/brand/logo";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { homeFor, safeNext, useAuthConfig, useMe } from "@/lib/hooks/auth";
import type { LoginResult } from "@/lib/types";

const PERSONA_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  priya: UserRound,
  meena: Stethoscope,
  arjun: UserRoundX,
  admin: ShieldCheck,
};

export function LoginPanel() {
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const router = useRouter();
  const qc = useQueryClient();
  const { data: config, isLoading: configLoading } = useAuthConfig();
  const { data: me } = useMe();
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || config?.google_client_id || "";

  // Already signed in? Skip the login screen.
  useEffect(() => {
    if (me) router.replace(me.role ? (next ?? homeFor(me)) : `/onboarding${next ? `?next=${encodeURIComponent(next)}` : ""}`);
  }, [me, next, router]);

  const finish = (result: LoginResult) => {
    qc.setQueryData(["me"], result.user);
    if (!result.user.role) {
      router.replace(`/onboarding${next ? `?next=${encodeURIComponent(next)}` : ""}`);
    } else {
      router.replace(next ?? result.redirect);
    }
  };

  const google = useMutation({
    mutationFn: (credential: string) => api.post<LoginResult>("/auth/google", { credential }),
    onSuccess: finish,
    onError: (e) => toast.error(`Sign-in failed: ${e.message}`),
  });
  const demo = useMutation({
    mutationFn: (persona: string) => api.post<LoginResult>("/auth/demo", { persona }),
    onSuccess: finish,
    onError: (e) => toast.error(`Demo sign-in failed: ${e.message}`),
  });
  const busy = google.isPending || demo.isPending;

  return (
    <div className="w-full max-w-sm space-y-4">
      <div className="lg:hidden">
        <Logo />
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Sign in to HealthThread</CardTitle>
          <CardDescription>
            {next?.startsWith("/share/")
              ? "Sign in to open the record someone shared with you."
              : "Patients, caregivers and doctors all use Google sign-in."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {configLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : clientId ? (
            <GoogleOAuthProvider clientId={clientId}>
              <div className="flex min-h-10 justify-center">
                <GoogleLogin
                  onSuccess={(r) => r.credential && google.mutate(r.credential)}
                  onError={() => toast.error("Google sign-in was cancelled or failed")}
                  text="continue_with"
                  shape="pill"
                  width="300"
                />
              </div>
            </GoogleOAuthProvider>
          ) : (
            <p className="rounded-lg border border-dashed px-3 py-2.5 text-center text-sm text-muted-foreground">
              Google sign-in isn&apos;t configured on this server yet. Set{" "}
              <code className="text-xs">GOOGLE_CLIENT_ID</code> in <code className="text-xs">.env</code>.
            </p>
          )}
          {google.isPending && (
            <p className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Signing you in…
            </p>
          )}
        </CardContent>
      </Card>

      {config?.demo_mode && (
        <Card className="border-warning/40">
          <CardHeader>
            <CardTitle className="text-base">Demo accounts</CardTitle>
            <CardDescription>One-click sign-in for judging. Synthetic data only.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2">
            {config.personas.map((p) => {
              const Icon = PERSONA_ICONS[p.key] ?? UserRound;
              return (
                <button
                  key={p.key}
                  disabled={busy}
                  onClick={() => demo.mutate(p.key)}
                  className="flex items-center gap-3 rounded-lg border bg-card px-3 py-2.5 text-left text-sm transition-colors hover:border-primary/40 hover:bg-accent/50 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-60"
                >
                  {demo.isPending && demo.variables === p.key ? (
                    <Loader2 className="size-4 animate-spin text-primary" />
                  ) : (
                    <Icon className="size-4 text-primary" />
                  )}
                  <span>{p.label}</span>
                </button>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
