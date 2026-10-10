"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pill } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { OrgChip } from "@/components/record/org-chip";
import { SourceList } from "@/components/record/source-list";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { orgColor, recordKeys, useMedications } from "@/lib/hooks/record";
import type { MedicationRow, OrgColors } from "@/lib/record-types";

export function MedicationsView({
  profileId,
  canStop = false,
  emptyAction,
}: {
  profileId: string;
  canStop?: boolean;
  emptyAction?: React.ReactNode;
}) {
  const { data, isLoading, isError, error, refetch } = useMedications(profileId);
  const [stopping, setStopping] = useState<MedicationRow | null>(null);
  if (isLoading) return <LoadingState rows={4} />;
  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;
  const meds = data?.medications ?? [];
  if (!meds.length)
    return (
      <EmptyState
        icon={Pill}
        title="No medicines recorded"
        description="Prescriptions you upload are read automatically. Brand names are matched to their generic medicine."
        action={emptyAction}
      />
    );
  const current = meds.filter((m) => m.status === "active");
  const past = meds.filter((m) => m.status !== "active");
  return (
    <div className="space-y-6">
      <section className="space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground">Current ({current.length})</h2>
        {current.length ? (
          <ul className="space-y-2">
            {current.map((m) => (
              <MedicationCard key={m.ref} med={m} colors={data!.org_colors} onStop={canStop ? () => setStopping(m) : undefined} />
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No current medicines.</p>
        )}
      </section>
      {past.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-medium text-muted-foreground">Past ({past.length})</h2>
          <ul className="space-y-2">
            {past.map((m) => (
              <MedicationCard key={m.ref} med={m} colors={data!.org_colors} />
            ))}
          </ul>
        </section>
      )}
      <StopDialog profileId={profileId} med={stopping} onClose={() => setStopping(null)} />
    </div>
  );
}

function MedicationCard({ med: m, colors, onStop }: { med: MedicationRow; colors: OrgColors; onStop?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-xl border bg-card">
      <div className="flex flex-wrap items-start gap-3 p-4">
        <Pill className={m.status === "active" ? "mt-0.5 size-5 text-primary" : "mt-0.5 size-5 text-muted-foreground"} />
        <div className="min-w-0 flex-1 space-y-1">
          <p className="font-medium">
            {m.display}
            {m.brand && <span className="font-normal text-muted-foreground"> · {m.brand}</span>}
          </p>
          <p className="text-sm text-muted-foreground">
            {m.frequency_label}
            {m.instructions ? ` · ${m.instructions}` : ""}
          </p>
          <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
            <OrgChip name={m.org} color={orgColor(colors, m.org)} />
            <span>
              Since {fmtDate(m.start)}
              {m.end ? ` · until ${fmtDate(m.end)}` : ""}
            </span>
            {m.status !== "active" && <Badge variant="secondary">{m.status}</Badge>}
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            Source
          </Button>
          {onStop && (
            <Button variant="outline" size="sm" onClick={onStop}>
              Mark as stopped
            </Button>
          )}
        </div>
      </div>
      {open && (
        <div className="border-t px-4 py-3">
          <SourceList sources={m.sources} colors={colors} />
          {!m.sources.length && m.requester && <p className="text-sm text-muted-foreground">Prescribed by {m.requester}.</p>}
        </div>
      )}
    </li>
  );
}

function StopDialog({ profileId, med, onClose }: { profileId: string; med: MedicationRow | null; onClose: () => void }) {
  const qc = useQueryClient();
  const stop = useMutation({
    mutationFn: () => api.post(`/profiles/${profileId}/medications/stop`, { ref: med?.ref }),
    onSuccess: () => {
      toast.success(`${med?.display} marked as stopped`);
      qc.invalidateQueries({ queryKey: recordKeys.all(profileId) });
      qc.invalidateQueries({ queryKey: ["alerts", profileId] });
      onClose();
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <Dialog open={!!med} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Mark {med?.display} as stopped?</DialogTitle>
          <DialogDescription>
            This updates the record only. Please discuss this with a doctor before changing any medicine.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => stop.mutate()} disabled={stop.isPending}>
            Mark as stopped
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
