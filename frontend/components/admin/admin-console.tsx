"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Check, FileText, Loader2, ShieldAlert, UserCheck, Users, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface DoctorRow {
  user_id: string;
  email: string;
  full_name: string;
  specialty: string;
  organization: string;
  council: string;
  registration_number: string;
  verification_status: "pending" | "verified" | "rejected";
  review_note: string | null;
  created_at: string;
  verified_at: string | null;
}

interface Stats {
  users: number;
  users_by_role: Record<string, number>;
  profiles: number;
  documents_processed: number;
  alerts_by_type: Record<string, number>;
  doctors_pending: number;
}

const TABS = ["pending", "verified", "rejected"] as const;

export function AdminConsole() {
  const [tab, setTab] = useState<(typeof TABS)[number]>("pending");
  const stats = useQuery({ queryKey: ["admin-stats"], queryFn: () => api.get<Stats>("/admin/stats") });
  const doctors = useQuery({
    queryKey: ["admin-doctors", tab],
    queryFn: () => api.get<DoctorRow[]>(`/admin/doctors?status_filter=${tab}`),
  });
  const [rejecting, setRejecting] = useState<DoctorRow | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Admin console"
        description="Verify clinicians and watch platform health. Admins never see patient records."
      />
      {stats.isError ? (
        <ErrorState error={stats.error} onRetry={() => stats.refetch()} />
      ) : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat icon={Users} label="Users" value={stats.data?.users} />
          <Stat icon={UserCheck} label="Health profiles" value={stats.data?.profiles} />
          <Stat icon={FileText} label="Documents processed" value={stats.data?.documents_processed} />
          <Stat icon={ShieldAlert} label="Doctors awaiting review" value={stats.data?.doctors_pending} highlight />
        </div>
      )}
      {stats.data && Object.keys(stats.data.alerts_by_type).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Safety alerts by type</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {Object.entries(stats.data.alerts_by_type).map(([t, n]) => (
              <Badge key={t} variant="secondary">
                {t.replace(/_/g, " ")}: {n}
              </Badge>
            ))}
          </CardContent>
        </Card>
      )}

      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="mr-auto font-medium">Doctor verification</h2>
          {TABS.map((t) => (
            <Button key={t} size="sm" variant={tab === t ? "default" : "outline"} onClick={() => setTab(t)}>
              {t[0].toUpperCase() + t.slice(1)}
            </Button>
          ))}
        </div>
        {doctors.isLoading ? (
          <LoadingState />
        ) : doctors.isError ? (
          <ErrorState error={doctors.error} onRetry={() => doctors.refetch()} />
        ) : !doctors.data?.length ? (
          <EmptyState icon={UserCheck} title={`No ${tab} doctors`} />
        ) : (
          <div className="space-y-2">
            {doctors.data.map((d) => (
              <DoctorCard key={d.user_id} doctor={d} onReject={() => setRejecting(d)} />
            ))}
          </div>
        )}
      </section>
      <RejectDialog doctor={rejecting} onClose={() => setRejecting(null)} />
    </div>
  );
}

function useVerify() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, note }: { id: string; decision: "approve" | "reject"; note?: string }) =>
      api.post<DoctorRow>(`/admin/doctors/${id}/verify`, { decision, note }),
    onSuccess: (d) => {
      toast.success(`${d.full_name} ${d.verification_status === "verified" ? "verified" : "rejected"}`);
      qc.invalidateQueries({ queryKey: ["admin-doctors"] });
      qc.invalidateQueries({ queryKey: ["admin-stats"] });
    },
    onError: (e) => toast.error(e.message),
  });
}

function DoctorCard({ doctor: d, onReject }: { doctor: DoctorRow; onReject: () => void }) {
  const verify = useVerify();
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-xl border bg-card p-4">
      <div className="min-w-0 flex-1 space-y-0.5">
        <p className="font-medium">
          {d.full_name} <span className="font-normal text-muted-foreground">· {d.specialty}</span>
        </p>
        <p className="text-sm text-muted-foreground">
          {d.organization} · {d.email}
        </p>
        <p className="text-sm">
          <span className="text-muted-foreground">{d.council}</span>{" "}
          <span className="font-mono">{d.registration_number}</span>
        </p>
        <p className="text-xs text-muted-foreground">Submitted {format(new Date(d.created_at), "d MMM yyyy, h:mm a")}</p>
        {d.review_note && <p className="text-xs text-muted-foreground">Note: {d.review_note}</p>}
      </div>
      {d.verification_status === "pending" && (
        <div className="flex gap-2">
          <Button variant="outline" onClick={onReject}>
            <X /> Reject
          </Button>
          <Button onClick={() => verify.mutate({ id: d.user_id, decision: "approve" })} disabled={verify.isPending}>
            {verify.isPending ? <Loader2 className="animate-spin" /> : <Check />} Approve
          </Button>
        </div>
      )}
    </div>
  );
}

function RejectDialog({ doctor, onClose }: { doctor: DoctorRow | null; onClose: () => void }) {
  const [note, setNote] = useState("");
  const verify = useVerify();
  return (
    <Dialog open={!!doctor} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reject {doctor?.full_name}?</DialogTitle>
          <DialogDescription>The doctor sees this note and can contact you to resubmit.</DialogDescription>
        </DialogHeader>
        <Field label="Reason" htmlFor="reject-note">
          <Textarea id="reject-note" value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={!note.trim() || verify.isPending}
            onClick={() =>
              doctor &&
              verify.mutate(
                { id: doctor.user_id, decision: "reject", note },
                {
                  onSuccess: () => {
                    setNote("");
                    onClose();
                  },
                },
              )
            }
          >
            Reject
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  highlight,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number | undefined;
  highlight?: boolean;
}) {
  return (
    <div className={cn("rounded-xl border bg-card p-4", highlight && value ? "border-warning/50 bg-warning-soft" : "")}>
      <Icon className="size-5 text-primary" />
      <p className="mt-2 text-2xl font-semibold">{value ?? "–"}</p>
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  );
}
