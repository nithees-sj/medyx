"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, QrCode, RefreshCw, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { AlertCard } from "@/components/record/alert-card";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAlerts, useOrgColors } from "@/lib/hooks/record";

export function AlertsView({ profileId }: { profileId: string }) {
  const all = useAlerts(profileId, "all");
  const colors = useOrgColors(profileId).data;
  const qc = useQueryClient();
  const rerun = useMutation({
    mutationFn: () => api.post<{ active: number; created: number }>(`/profiles/${profileId}/alerts/rerun`),
    onSuccess: (r) => {
      toast.success(r.created ? `${r.created} new alert${r.created > 1 ? "s" : ""}` : "Checks re-run — nothing new");
      qc.invalidateQueries({ queryKey: ["alerts", profileId] });
      qc.invalidateQueries({ queryKey: ["profile", profileId] });
    },
    onError: (e) => toast.error(e.message),
  });

  if (all.isLoading) return <LoadingState rows={3} />;
  if (all.isError) return <ErrorState error={all.error} onRetry={() => all.refetch()} />;
  const active = (all.data ?? []).filter((a) => a.status === "active");
  const past = (all.data ?? []).filter((a) => a.status !== "active");

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-xl text-sm text-muted-foreground">
          HealthThread checks your whole record across every hospital for duplicate medicines, allergy conflicts, side-effect
          cascades and slow changes in lab results. These are things to discuss with a doctor, not instructions.
        </p>
        <Button variant="outline" size="sm" onClick={() => rerun.mutate()} disabled={rerun.isPending}>
          {rerun.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />} Re-run checks
        </Button>
      </div>
      {active.length === 0 ? (
        <EmptyState icon={ShieldCheck} title="No active alerts" description="Nothing in the record needs attention right now." />
      ) : (
        <div className="space-y-3">
          {active.map((a) => (
            <AlertCard
              key={a.id}
              alert={a}
              colors={colors}
              audience="patient"
              actions={
                <Link href={`/app/p/${profileId}/sharing?from=alert`} className={buttonVariants({ size: "sm" })}>
                  <QrCode /> Show this to my doctor
                </Link>
              }
            />
          ))}
        </div>
      )}
      {past.length > 0 && (
        <details className="rounded-xl border bg-card">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium select-none">Reviewed and resolved ({past.length})</summary>
          <div className="space-y-3 border-t p-4">
            {past.map((a) => (
              <AlertCard key={a.id} alert={a} colors={colors} audience="patient" />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
