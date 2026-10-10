"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AlertCard } from "@/components/record/alert-card";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAlerts, useOrgColors } from "@/lib/hooks/record";
import type { AlertRow } from "@/lib/record-types";

export function DoctorAlertsTab({ profileId }: { profileId: string }) {
  const q = useAlerts(profileId, "all");
  const colors = useOrgColors(profileId).data;
  const qc = useQueryClient();
  const [reviewing, setReviewing] = useState<AlertRow | null>(null);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["alerts", profileId] });
    qc.invalidateQueries({ queryKey: ["profile", profileId] });
    qc.invalidateQueries({ queryKey: ["doctor-patients"] });
  };
  const resolve = useMutation({
    mutationFn: (id: string) => api.post(`/alerts/${id}/review`, { status: "resolved" }),
    onSuccess: refresh,
    onError: (e) => toast.error(e.message),
  });
  const rerun = useMutation({ mutationFn: () => api.post(`/profiles/${profileId}/alerts/rerun`), onSuccess: refresh });

  if (q.isLoading) return <LoadingState rows={3} />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const active = (q.data ?? []).filter((a) => a.status === "active");
  const reviewed = (q.data ?? []).filter((a) => a.status !== "active");
  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={() => rerun.mutate()} disabled={rerun.isPending}>
          {rerun.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />} Re-run checks
        </Button>
      </div>
      {!active.length && <EmptyState icon={ShieldCheck} title="No active alerts" description="Nothing flagged in the shared record." />}
      {active.map((a) => (
        <AlertCard
          key={a.id}
          alert={a}
          colors={colors}
          audience="doctor"
          actions={
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setReviewing(a)}>
                <CheckCheck /> Reviewed — intentional
              </Button>
              <Button size="sm" variant="ghost" onClick={() => resolve.mutate(a.id)} disabled={resolve.isPending}>
                Resolve
              </Button>
            </div>
          }
        />
      ))}
      {reviewed.length > 0 && (
        <details className="rounded-xl border bg-card">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium select-none">Reviewed / resolved ({reviewed.length})</summary>
          <div className="space-y-3 border-t p-4">
            {reviewed.map((a) => (
              <AlertCard key={a.id} alert={a} colors={colors} audience="doctor" />
            ))}
          </div>
        </details>
      )}
      <ReviewDialog alert={reviewing} onClose={() => setReviewing(null)} onDone={refresh} />
    </div>
  );
}

function ReviewDialog({ alert, onClose, onDone }: { alert: AlertRow | null; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState("");
  const save = useMutation({
    mutationFn: () => api.post(`/alerts/${alert?.id}/review`, { status: "reviewed_intentional", note }),
    onSuccess: () => {
      toast.success("Marked as reviewed — it stays quiet unless the evidence changes");
      setNote("");
      onDone();
      onClose();
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <Dialog open={!!alert} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reviewed — intentional</DialogTitle>
          <DialogDescription>{alert?.title}</DialogDescription>
        </DialogHeader>
        <Field label="Why is this intentional?" htmlFor="review-note">
          <Textarea id="review-note" value={note} onChange={(e) => setNote(e.target.value)} rows={3} placeholder="e.g. Glucophage replaces Glycomet; patient told to stop Glycomet." />
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => save.mutate()} disabled={!note.trim() || save.isPending}>
            Save review
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
