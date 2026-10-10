"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNowStrict } from "date-fns";
import { BadgeCheck, CheckCircle2, Copy, Loader2, Lock, QrCode, ShieldAlert, Stethoscope, X } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Countdown } from "@/components/ui/countdown";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { fmtInstant } from "@/lib/format";
import {
  type ConsentRow,
  DEFAULT_SCOPES,
  DURATIONS,
  type Scope,
  SCOPE_LABEL,
  SCOPES,
  useConsents,
} from "@/lib/hooks/consents";
import { cn } from "@/lib/utils";

interface ShareResult {
  consent: ConsentRow;
  token: string;
  url: string;
}

export function SharingView({ profileId }: { profileId: string }) {
  const [share, setShare] = useState<ShareResult | null>(null);
  const consents = useConsents(profileId, !!share);
  const list = consents.data ?? [];
  const requested = list.filter((c) => c.status === "requested");
  const active = list.filter((c) => c.status === "active");
  const history = list.filter((c) => ["revoked", "expired", "denied"].includes(c.status));

  return (
    <div className="space-y-6">
      {requested.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-medium text-muted-foreground">Requests waiting for you</h2>
          {requested.map((c) => (
            <RequestCard key={c.id} profileId={profileId} consent={c} />
          ))}
        </section>
      )}

      <ShareCard profileId={profileId} share={share} setShare={setShare} consents={list} />

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground">Doctors who can see this record</h2>
        {consents.isLoading ? (
          <LoadingState rows={2} />
        ) : consents.isError ? (
          <ErrorState error={consents.error} onRetry={() => consents.refetch()} />
        ) : active.length === 0 ? (
          <EmptyState icon={Lock} title="Only you can see this record" description="Share with a doctor using a QR code above." />
        ) : (
          active.map((c) => <ActiveConsent key={c.id} profileId={profileId} consent={c} />)
        )}
      </section>

      {history.length > 0 && (
        <details className="rounded-xl border bg-card">
          <summary className="cursor-pointer px-4 py-3 text-sm font-medium select-none">Past sharing ({history.length})</summary>
          <ul className="divide-y border-t">
            {history.map((c) => (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                <span>
                  {c.doctor ? `${c.doctor.name} · ${c.doctor.specialty}` : "Unclaimed QR code"}
                  <span className="block text-xs text-muted-foreground">{c.scopes.map((s) => SCOPE_LABEL[s]).join(", ")}</span>
                </span>
                <Badge variant="secondary">
                  {c.status}
                  {c.revoked_at ? ` · ${fmtInstant(c.revoked_at, "d MMM, h:mm a")}` : ""}
                </Badge>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function ScopePicker({ value, onChange, allowed }: { value: Scope[]; onChange: (v: Scope[]) => void; allowed?: Scope[] }) {
  const options = allowed ?? SCOPES;
  return (
    <fieldset className="grid gap-2 sm:grid-cols-2">
      <legend className="mb-2 text-sm font-medium">What they can see</legend>
      {options.map((s) => {
        const checked = value.includes(s);
        return (
          <label
            key={s}
            className={cn(
              "flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2 text-sm",
              checked ? "border-primary/50 bg-accent/40" : "bg-card",
              s === "mental_health" && "border-dashed",
            )}
          >
            <Checkbox checked={checked} onCheckedChange={(c) => onChange(c ? [...value, s] : value.filter((x) => x !== s))} />
            <span>
              {SCOPE_LABEL[s]}
              {s === "mental_health" && <span className="block text-xs text-muted-foreground">Sensitive — off unless you choose it</span>}
            </span>
          </label>
        );
      })}
      <p className="text-xs text-muted-foreground sm:col-span-2">Name, age and sex are always included.</p>
    </fieldset>
  );
}

function ShareCard({
  profileId,
  share,
  setShare,
  consents,
}: {
  profileId: string;
  share: ShareResult | null;
  setShare: (s: ShareResult | null) => void;
  consents: ConsentRow[];
}) {
  const qc = useQueryClient();
  const [scopes, setScopes] = useState<Scope[]>(DEFAULT_SCOPES);
  const [hours, setHours] = useState(168);
  const [canWrite, setCanWrite] = useState(false);
  const [expired, setExpired] = useState(false);
  const create = useMutation({
    mutationFn: () =>
      api.post<ShareResult>(`/profiles/${profileId}/shares`, { scopes, duration_hours: hours, can_write: canWrite }),
    onSuccess: (r) => {
      setExpired(false);
      setShare(r);
      qc.invalidateQueries({ queryKey: ["consents", profileId] });
    },
    onError: (e) => toast.error(e.message),
  });
  const live = share ? consents.find((c) => c.id === share.consent.id) : null;
  const claimed = live?.status === "active";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <QrCode className="size-5 text-primary" /> Share with a doctor
        </CardTitle>
        <CardDescription>The doctor scans the QR code, signs in, and sees only what you choose, for as long as you choose.</CardDescription>
      </CardHeader>
      <CardContent>
        {share ? (
          claimed ? (
            <div className="flex flex-col items-center gap-3 py-6 text-center">
              <CheckCircle2 className="size-12 text-success" />
              <p className="text-lg font-semibold">{live?.doctor?.name} is connected</p>
              <p className="text-sm text-muted-foreground">
                {live?.doctor?.specialty} · access ends {live?.expires_at ? fmtInstant(live.expires_at, "d MMM, h:mm a") : ""}
              </p>
              <Button variant="outline" onClick={() => setShare(null)}>
                Done
              </Button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-4 py-2 text-center">
              <div className={cn("rounded-2xl border bg-white p-4", expired && "opacity-30")}>
                <QRCodeSVG value={share.url} size={232} marginSize={1} aria-label="Share QR code" />
              </div>
              {expired ? (
                <p className="text-sm text-critical">This QR code expired. Create a new one.</p>
              ) : (
                <p className="flex items-center gap-2 text-sm">
                  <Loader2 className="size-4 animate-spin text-primary" /> Waiting for the doctor to scan · expires in{" "}
                  <Countdown until={share.consent.claim_deadline as string} onExpire={() => setExpired(true)} />
                </p>
              )}
              <p className="max-w-sm text-xs text-muted-foreground">
                {share.consent.scopes.map((s) => SCOPE_LABEL[s]).join(", ")} ·{" "}
                {DURATIONS.find((d) => d.hours === share.consent.duration_hours)?.label}
                {share.consent.can_write ? " · can add documents & prescriptions" : " · read-only"}
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => navigator.clipboard.writeText(share.url).then(() => toast.success("Link copied"))}
                >
                  <Copy /> Copy link
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setShare(null)}>
                  <X /> Cancel
                </Button>
              </div>
            </div>
          )
        ) : (
          <form
            className="space-y-5"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <ScopePicker value={scopes} onChange={setScopes} />
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor="share-duration">For how long</Label>
                <NativeSelect id="share-duration" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
                  {DURATIONS.map((d) => (
                    <option key={d.hours} value={d.hours}>
                      {d.label}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <label className="flex items-center justify-between gap-3 rounded-lg border bg-card px-3 py-2 text-sm">
                <span>
                  Allow doctor to add documents & prescriptions
                  <span className="block text-xs text-muted-foreground">Off = read-only</span>
                </span>
                <Switch checked={canWrite} onCheckedChange={setCanWrite} aria-label="Allow doctor to add documents and prescriptions" />
              </label>
            </div>
            {scopes.includes("mental_health") && (
              <p className="flex gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm">
                <ShieldAlert className="size-4 shrink-0 text-warning" /> Mental-health information will be visible to this doctor.
              </p>
            )}
            <Button type="submit" size="lg" disabled={!scopes.length || create.isPending}>
              {create.isPending ? <Loader2 className="animate-spin" /> : <QrCode />} Create QR code
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

function DoctorLine({ c }: { c: ConsentRow }) {
  if (!c.doctor) return null;
  return (
    <div className="flex items-start gap-3">
      <Stethoscope className="mt-0.5 size-5 text-primary" />
      <div>
        <p className="font-medium">
          {c.doctor.name}{" "}
          {c.doctor.verified && (
            <span className="inline-flex items-center gap-0.5 align-middle text-xs font-normal text-success">
              <BadgeCheck className="size-3.5" /> Verified
            </span>
          )}
        </p>
        <p className="text-sm text-muted-foreground">
          {c.doctor.specialty} · {c.doctor.organization}
        </p>
      </div>
    </div>
  );
}

function ActiveConsent({ profileId, consent: c }: { profileId: string; consent: ConsentRow }) {
  const qc = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const revoke = useMutation({
    mutationFn: () => api.post(`/consents/${c.id}/revoke`),
    onSuccess: () => {
      toast.success(`${c.doctor?.name}'s access was revoked`);
      setConfirm(false);
      qc.invalidateQueries({ queryKey: ["consents", profileId] });
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border bg-card p-4">
      <div className="space-y-2">
        <DoctorLine c={c} />
        <div className="flex flex-wrap gap-1">
          {c.scopes.map((s) => (
            <Badge key={s} variant="secondary">
              {SCOPE_LABEL[s]}
            </Badge>
          ))}
          {c.can_write && <Badge variant="outline">Can add documents</Badge>}
        </div>
        <p className="text-xs text-muted-foreground">
          Ends in {c.expires_at ? formatDistanceToNowStrict(new Date(c.expires_at)) : "—"} ({c.expires_at ? fmtInstant(c.expires_at) : ""})
        </p>
      </div>
      <Button variant="destructive" onClick={() => setConfirm(true)}>
        Revoke
      </Button>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke {c.doctor?.name}&apos;s access?</DialogTitle>
            <DialogDescription>This takes effect immediately. You can share again any time.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => revoke.mutate()} disabled={revoke.isPending}>
              {revoke.isPending && <Loader2 className="animate-spin" />} Revoke access
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function RequestCard({ profileId, consent: c }: { profileId: string; consent: ConsentRow }) {
  const qc = useQueryClient();
  const [scopes, setScopes] = useState<Scope[]>(c.scopes);
  const [hours, setHours] = useState(c.duration_hours);
  const [canWrite, setCanWrite] = useState(false);
  const done = () => qc.invalidateQueries({ queryKey: ["consents", profileId] });
  const approve = useMutation({
    mutationFn: () => api.post(`/consents/${c.id}/approve`, { scopes, duration_hours: hours, can_write: canWrite }),
    onSuccess: () => {
      toast.success("Access approved");
      done();
    },
    onError: (e) => toast.error(e.message),
  });
  const deny = useMutation({
    mutationFn: () => api.post(`/consents/${c.id}/deny`),
    onSuccess: () => {
      toast.success("Request declined");
      done();
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <div className="space-y-4 rounded-xl border border-primary/30 bg-card p-4">
      <DoctorLine c={c} />
      {c.purpose && <p className="text-sm">“{c.purpose}”</p>}
      <ScopePicker value={scopes} onChange={setScopes} allowed={c.scopes} />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label htmlFor={`dur-${c.id}`}>For how long</Label>
          <NativeSelect id={`dur-${c.id}`} value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            {DURATIONS.filter((d) => d.hours <= c.duration_hours).map((d) => (
              <option key={d.hours} value={d.hours}>
                {d.label}
              </option>
            ))}
          </NativeSelect>
        </div>
        <label className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm">
          Allow adding documents & prescriptions
          <Switch checked={canWrite} onCheckedChange={setCanWrite} aria-label="Allow adding documents and prescriptions" />
        </label>
      </div>
      <div className="flex gap-2">
        <Button onClick={() => approve.mutate()} disabled={!scopes.length || approve.isPending}>
          {approve.isPending && <Loader2 className="animate-spin" />} Approve
        </Button>
        <Button variant="outline" onClick={() => deny.mutate()} disabled={deny.isPending}>
          Decline
        </Button>
      </div>
    </div>
  );
}
