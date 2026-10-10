"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Send, UserSearch } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { api } from "@/lib/api";
import { fmtInstant } from "@/lib/format";
import { DEFAULT_SCOPES, DURATIONS, type Scope, SCOPE_LABEL, SCOPES } from "@/lib/hooks/consents";

interface RequestRow {
  id: string;
  status: "requested" | "denied";
  healththread_id: string;
  scopes: Scope[];
  duration_hours: number;
  purpose: string | null;
  created_at: string;
}

export function RequestsView() {
  const qc = useQueryClient();
  const requests = useQuery({ queryKey: ["doctor-requests"], queryFn: () => api.get<RequestRow[]>("/doctor/requests") });
  const [identifier, setIdentifier] = useState("");
  const [scopes, setScopes] = useState<Scope[]>(DEFAULT_SCOPES);
  const [hours, setHours] = useState(168);
  const [purpose, setPurpose] = useState("");
  const send = useMutation({
    mutationFn: () => api.post("/doctor/requests", { identifier, scopes, duration_hours: hours, purpose: purpose || null }),
    onSuccess: () => {
      toast.success("Request sent. The patient will see it in their app.");
      setIdentifier("");
      setPurpose("");
      qc.invalidateQueries({ queryKey: ["doctor-requests"] });
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <div className="space-y-6">
      <PageHeader title="Request access" description="Ask a patient for access by their HealthThread ID or the exact email of their account." />
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <UserSearch className="size-5 text-primary" /> Find a patient
          </CardTitle>
          <CardDescription>Exact matches only. HealthThread never lists or suggests patients.</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              send.mutate();
            }}
          >
            <Field label="HealthThread ID or email" htmlFor="identifier">
              <Input id="identifier" placeholder="HT-7K2P-9QX4" value={identifier} onChange={(e) => setIdentifier(e.target.value)} required />
            </Field>
            <fieldset className="grid gap-2 sm:grid-cols-3">
              <legend className="mb-2 text-sm font-medium">Requested access</legend>
              {SCOPES.map((s) => (
                <label key={s} className="flex items-center gap-2 text-sm">
                  <Checkbox checked={scopes.includes(s)} onCheckedChange={(c) => setScopes(c ? [...scopes, s] : scopes.filter((x) => x !== s))} />
                  {SCOPE_LABEL[s]}
                </label>
              ))}
            </fieldset>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Duration" htmlFor="duration">
                <NativeSelect id="duration" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
                  {DURATIONS.map((d) => (
                    <option key={d.hours} value={d.hours}>
                      {d.label}
                    </option>
                  ))}
                </NativeSelect>
              </Field>
              <Field label="Reason (shown to the patient)" htmlFor="purpose">
                <Input id="purpose" placeholder="Kidney function review" value={purpose} onChange={(e) => setPurpose(e.target.value)} />
              </Field>
            </div>
            <Button type="submit" disabled={!identifier || !scopes.length || send.isPending}>
              {send.isPending ? <Loader2 className="animate-spin" /> : <Send />} Send request
            </Button>
          </form>
        </CardContent>
      </Card>
      <section className="space-y-2">
        <h2 className="font-medium">Your requests</h2>
        {requests.isLoading ? (
          <LoadingState rows={2} />
        ) : requests.isError ? (
          <ErrorState error={requests.error} onRetry={() => requests.refetch()} />
        ) : !requests.data?.length ? (
          <EmptyState title="No pending requests" description="Approved requests appear on your dashboard as patients." />
        ) : (
          <ul className="divide-y rounded-xl border bg-card">
            {requests.data.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                <span>
                  <span className="font-mono">{r.healththread_id}</span>
                  <span className="block text-xs text-muted-foreground">
                    {r.scopes.map((s) => SCOPE_LABEL[s]).join(", ")} · sent {fmtInstant(r.created_at)}
                  </span>
                </span>
                <Badge variant={r.status === "denied" ? "destructive" : "secondary"}>
                  {r.status === "denied" ? "Declined" : "Waiting for patient"}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
