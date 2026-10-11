"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, Globe, Loader2, RefreshCw, ShieldOff, ShieldPlus, Trash2, UserCheck, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { CHECK_TITLE, CheckStatus, Panel, RiskBadge, StatusPill } from "@/components/admin/ui";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/states";
import { Button, buttonVariants } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { fmtInstant } from "@/lib/format";
import { type DoctorRow, useDoctors, useTrustedDomains, useVerificationConfig } from "@/lib/hooks/admin";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "pending", label: "Needs review" },
  { key: "verified", label: "Verified" },
  { key: "suspended", label: "Suspended" },
  { key: "rejected", label: "Rejected" },
] as const;

type NoteAction = { doctor: DoctorRow; action: "reject" | "suspend" | "reinstate" } | null;

export function DoctorVerification() {
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("pending");
  const doctors = useDoctors(tab);
  const [noteAction, setNoteAction] = useState<NoteAction>(null);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Doctor verification"
        description="Every application is checked automatically against the medical register, trusted hospital email domains, the uploaded certificate and other accounts. Clear-cut cases are decided by the rules; everything else waits here with its evidence."
      />
      <AutomationStatus />

      <section className="space-y-3">
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Verification status">
          {TABS.map((t) => (
            <Button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              size="sm"
              variant={tab === t.key ? "default" : "outline"}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </Button>
          ))}
        </div>
        {doctors.isLoading ? (
          <LoadingState />
        ) : doctors.isError ? (
          <ErrorState error={doctors.error} onRetry={() => doctors.refetch()} />
        ) : !doctors.data?.length ? (
          <EmptyState
            icon={UserCheck}
            title={tab === "pending" ? "No applications waiting" : `No ${tab} doctors`}
            description={tab === "pending" ? "New applications appear here with their automated checks." : undefined}
          />
        ) : (
          <div className="space-y-3">
            {doctors.data.map((d) => (
              <DoctorCard key={d.user_id} doctor={d} onNote={(action) => setNoteAction({ doctor: d, action })} />
            ))}
          </div>
        )}
      </section>

      <TrustedDomains />
      <NoteDialog value={noteAction} onClose={() => setNoteAction(null)} />
    </div>
  );
}

function AutomationStatus() {
  const { data } = useVerificationConfig();
  if (!data) return null;
  const r = data.registry;
  return (
    <div className={cn("rounded-xl border p-4 text-sm", r.configured ? "bg-card" : "border-warning/40 bg-warning-soft")}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusPill ok={r.configured ? true : null} label={r.configured ? `Medical register connected (${r.url_host ?? r.provider})` : "Medical register not connected"} />
        <StatusPill ok={data.auto_approve} label={data.auto_approve ? "Auto-approve on" : "Auto-approve off"} />
        <StatusPill ok={data.auto_reject} label={data.auto_reject ? "Auto-reject on" : "Auto-reject off"} />
        <span className="text-xs text-muted-foreground">Verified doctors are re-checked every {data.recheck_days} days.</span>
      </div>
      {!r.configured && (
        <p className="mt-2 text-muted-foreground">
          Without a register connection nothing is approved automatically; certificates, work emails and duplicate checks are still
          collected so reviews take seconds. Set <code className="text-xs">REGISTRY_PROVIDER=http</code> and{" "}
          <code className="text-xs">REGISTRY_URL</code> (see docs/VERIFICATION.md) to enable automatic decisions.
        </p>
      )}
    </div>
  );
}

function useDoctorAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, path, body }: { id: string; path: string; body?: unknown }) =>
      api.post<DoctorRow>(`/admin/doctors/${id}/${path}`, body ?? {}),
    onSuccess: (d, v) => {
      const msg = {
        verify: d.verification_status === "verified" ? "verified" : "rejected",
        recheck: "re-checked",
        suspend: "suspended",
        reinstate: "reinstated",
      }[v.path];
      toast.success(`${d.full_name} ${msg}`);
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (e) => toast.error(e.message),
  });
}

function DoctorCard({ doctor: d, onNote }: { doctor: DoctorRow; onNote: (a: "reject" | "suspend" | "reinstate") => void }) {
  const act = useDoctorAction();
  const busy = act.isPending;
  const doc = d.checks.find((c) => c.kind === "document");
  const read = (doc?.details?.read ?? null) as Record<string, string | null> | null;

  return (
    <article className="rounded-xl border bg-card p-4">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1 space-y-0.5">
          <p className="font-medium">
            {d.full_name} <span className="font-normal text-muted-foreground">· {d.specialty}</span>
          </p>
          <p className="text-sm text-muted-foreground">
            {d.organization} · {d.email}
          </p>
          <p className="text-sm">
            <span className="text-muted-foreground">{d.council}</span> <span className="font-mono">{d.registration_number}</span>
          </p>
          <p className="text-xs text-muted-foreground">
            Applied {fmtInstant(d.created_at, "d MMM yyyy, h:mm a")}
            {d.last_checked_at && ` · checked ${fmtInstant(d.last_checked_at, "d MMM, h:mm a")}`}
            {d.verified_at && d.verification_status !== "pending" && ` · decided ${fmtInstant(d.verified_at, "d MMM yyyy")}`}
            {d.verification_method && ` · by ${d.verification_method}`}
            {d.next_check_at && ` · next register check ${fmtInstant(d.next_check_at, "d MMM yyyy")}`}
          </p>
        </div>
        {d.verification_status === "pending" && <RiskBadge risk={d.risk} />}
      </div>

      {d.reasons.length > 0 && (
        <ul className="mt-3 list-disc space-y-0.5 pl-5 text-sm">
          {d.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
      {d.review_note && d.verification_status !== "pending" && (
        <p className="mt-2 text-sm text-muted-foreground">Note: {d.review_note}</p>
      )}

      {d.checks.length > 0 && (
        <ul className="mt-3 divide-y rounded-lg border">
          {d.checks.map((c) => (
            <li key={c.kind} className="flex flex-wrap items-start gap-x-3 gap-y-1 px-3 py-2 text-sm">
              <span className="w-36 shrink-0 font-medium">{CHECK_TITLE[c.kind]}</span>
              <CheckStatus status={c.status} />
              <span className="min-w-0 flex-1 basis-60 text-muted-foreground">{c.summary}</span>
            </li>
          ))}
        </ul>
      )}

      {read && (
        <div className="mt-3 rounded-lg bg-muted/50 p-3 text-xs">
          <p className="mb-1 font-medium">Read from the certificate (AI — evidence only)</p>
          <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-3">
            {(["full_name", "registration_number", "council", "issuer", "qualification", "registration_date"] as const).map((k) =>
              read[k] ? (
                <div key={k}>
                  <dt className="text-muted-foreground">{k.replace(/_/g, " ")}</dt>
                  <dd className="font-medium">{read[k]}</dd>
                </div>
              ) : null,
            )}
          </dl>
          {Array.isArray(doc?.details?.concerns) && (doc!.details.concerns as string[]).length > 0 && (
            <p className="mt-2 text-warning">Reader noted: {(doc!.details.concerns as string[]).join("; ")}</p>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {d.certificate && (
          <a
            href={`/api/admin/doctors/${d.user_id}/certificate`}
            target="_blank"
            rel="noreferrer"
            className={buttonVariants({ variant: "ghost", size: "sm" })}
          >
            <ExternalLink /> {d.certificate.reading ? "Certificate (reading…)" : "View certificate"}
          </a>
        )}
        <span className="flex-1" />
        <Button variant="outline" size="sm" onClick={() => act.mutate({ id: d.user_id, path: "recheck" })} disabled={busy}>
          <RefreshCw className={cn(busy && "animate-spin")} /> Re-run checks
        </Button>
        {d.verification_status === "pending" && (
          <>
            <Button variant="outline" size="sm" onClick={() => onNote("reject")} disabled={busy}>
              <X /> Reject
            </Button>
            <Button size="sm" onClick={() => act.mutate({ id: d.user_id, path: "verify", body: { decision: "approve" } })} disabled={busy}>
              <Check /> Approve
            </Button>
          </>
        )}
        {d.verification_status === "verified" && (
          <Button variant="outline" size="sm" onClick={() => onNote("suspend")} disabled={busy}>
            <ShieldOff /> Suspend
          </Button>
        )}
        {d.verification_status === "suspended" && (
          <Button size="sm" onClick={() => onNote("reinstate")} disabled={busy}>
            <ShieldPlus /> Reinstate
          </Button>
        )}
      </div>
    </article>
  );
}

const NOTE_COPY = {
  reject: {
    title: "Reject",
    help: "The doctor sees this note and can correct their details to resubmit.",
    button: "Reject",
    required: true,
  },
  suspend: {
    title: "Suspend",
    help: "Ends every active patient share immediately and notifies those patients. The doctor sees this reason.",
    button: "Suspend",
    required: true,
  },
  reinstate: {
    title: "Reinstate",
    help: "Restores access to the portal. Shares ended by the suspension stay ended; patients can share again.",
    button: "Reinstate",
    required: false,
  },
};

function NoteDialog({ value, onClose }: { value: NoteAction; onClose: () => void }) {
  const [note, setNote] = useState("");
  const act = useDoctorAction();
  const copy = value ? NOTE_COPY[value.action] : null;
  return (
    <Dialog open={!!value} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {copy?.title} {value?.doctor.full_name}?
          </DialogTitle>
          <DialogDescription>{copy?.help}</DialogDescription>
        </DialogHeader>
        <Field label={copy?.required ? "Reason" : "Note (optional)"} htmlFor="admin-note">
          <Textarea id="admin-note" value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant={value?.action === "reinstate" ? "default" : "destructive"}
            disabled={(copy?.required && !note.trim()) || act.isPending}
            onClick={() =>
              value &&
              act.mutate(
                value.action === "reject"
                  ? { id: value.doctor.user_id, path: "verify", body: { decision: "reject", note } }
                  : { id: value.doctor.user_id, path: value.action, body: { note } },
                {
                  onSuccess: () => {
                    setNote("");
                    onClose();
                  },
                },
              )
            }
          >
            {act.isPending && <Loader2 className="animate-spin" />} {copy?.button}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TrustedDomains() {
  const qc = useQueryClient();
  const domains = useTrustedDomains();
  const [form, setForm] = useState({ domain: "", organization: "" });
  const add = useMutation({
    mutationFn: () => api.post("/admin/trusted-domains", form),
    onSuccess: () => {
      toast.success(`@${form.domain.replace(/^@/, "")} is now trusted`);
      setForm({ domain: "", organization: "" });
      qc.invalidateQueries({ queryKey: ["admin", "trusted-domains"] });
    },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (d: string) => api.del(`/admin/trusted-domains/${encodeURIComponent(d)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "trusted-domains"] }),
    onError: (e) => toast.error(e.message),
  });
  return (
    <Panel
      title="Trusted hospital email domains"
      description="Google confirms each user owns their email address, so a doctor signing in from one of these domains is tied to that hospital. Never add public providers like gmail.com."
    >
      <form
        className="mb-4 grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate();
        }}
      >
        <Field label="Domain" htmlFor="td-domain">
          <Input id="td-domain" placeholder="kaverikidney.in" value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} required />
        </Field>
        <Field label="Hospital / organisation" htmlFor="td-org">
          <Input
            id="td-org"
            placeholder="Kaveri Kidney Care"
            value={form.organization}
            onChange={(e) => setForm({ ...form, organization: e.target.value })}
            required
          />
        </Field>
        <Button type="submit" disabled={add.isPending}>
          {add.isPending ? <Loader2 className="animate-spin" /> : <Globe />} Trust domain
        </Button>
      </form>
      {domains.data?.length ? (
        <ul className="divide-y text-sm">
          {domains.data.map((d) => (
            <li key={d.domain} className="flex items-center gap-3 py-2">
              <span className="font-mono">@{d.domain}</span>
              <span className="flex-1 text-muted-foreground">{d.organization}</span>
              <Button variant="ghost" size="icon-sm" aria-label={`Remove ${d.domain}`} onClick={() => remove.mutate(d.domain)}>
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">No trusted domains yet.</p>
      )}
    </Panel>
  );
}
