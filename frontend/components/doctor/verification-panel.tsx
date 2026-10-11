"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Loader2, Pencil } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { CHECK_TITLE, CheckStatus } from "@/components/admin/ui";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { ApiError, api } from "@/lib/api";
import { fmtInstant } from "@/lib/format";
import type { CheckRow } from "@/lib/hooks/admin";
import { useAuthConfig } from "@/lib/hooks/auth";
import type { DoctorInfo } from "@/lib/types";

interface MyVerification {
  status: DoctorInfo["verification_status"];
  method: string | null;
  review_note: string | null;
  checked_at: string | null;
  in_progress: boolean;
  certificate: { filename: string; uploaded_at: string } | null;
  checks: CheckRow[];
  can_update: boolean;
}

/** The doctor's view of their own verification: what was checked, and how to move it along. */
export function VerificationPanel({ doctor }: { doctor: DoctorInfo }) {
  const qc = useQueryClient();
  const v = useQuery({
    queryKey: ["my-verification"],
    queryFn: () => api.get<MyVerification>("/doctor/verification"),
    refetchInterval: (q) => (q.state.data?.in_progress || q.state.data?.status === "pending" ? 5_000 : false),
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["my-verification"] });
    qc.invalidateQueries({ queryKey: ["me"] });
  };
  const [editing, setEditing] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return api.post("/doctor/verification/certificate", fd);
    },
    onSuccess: () => {
      toast.success("Certificate uploaded — reading it now");
      refresh();
    },
    onError: (e) => toast.error(e.message),
  });

  if (doctor.verification_status === "verified" || !v.data) return null;
  const d = v.data;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">What we&apos;ve checked</CardTitle>
        <CardDescription>
          HealthThread checks your registration automatically
          {d.checked_at ? ` (last run ${fmtInstant(d.checked_at, "d MMM, h:mm a")})` : ""}. A registration certificate and a
          hospital work email make the review faster.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {d.checks.length ? (
          <ul className="divide-y rounded-lg border">
            {d.checks.map((c) => (
              <li key={c.kind} className="flex flex-wrap items-start gap-x-3 gap-y-1 px-3 py-2 text-sm">
                <span className="w-36 shrink-0 font-medium">{CHECK_TITLE[c.kind]}</span>
                <CheckStatus status={c.status} />
                <span className="min-w-0 flex-1 basis-56 text-muted-foreground">{c.summary}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Running the checks…
          </p>
        )}

        {d.can_update && (
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf,image/png,image/jpeg"
              className="hidden"
              aria-label="Registration certificate"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload.mutate(f);
                e.target.value = "";
              }}
            />
            <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={upload.isPending || d.in_progress}>
              {upload.isPending || d.in_progress ? <Loader2 className="animate-spin" /> : <FileUp />}
              {d.in_progress ? "Reading your certificate…" : d.certificate ? "Upload a different certificate" : "Upload registration certificate"}
            </Button>
            <Button variant="ghost" onClick={() => setEditing((x) => !x)}>
              <Pencil /> {editing ? "Cancel" : "Correct my details"}
            </Button>
            {d.certificate && !d.in_progress && (
              <span className="text-xs text-muted-foreground">
                {d.certificate.filename} · uploaded {fmtInstant(d.certificate.uploaded_at, "d MMM")}
              </span>
            )}
          </div>
        )}
        {editing && (
          <DetailsForm
            doctor={doctor}
            onDone={() => {
              setEditing(false);
              refresh();
            }}
          />
        )}
      </CardContent>
    </Card>
  );
}

function DetailsForm({ doctor, onDone }: { doctor: DoctorInfo; onDone: () => void }) {
  const { data: config } = useAuthConfig();
  const [form, setForm] = useState({
    full_name: doctor.full_name,
    specialty: doctor.specialty,
    organization: doctor.organization,
    council: doctor.council,
    registration_number: doctor.registration_number,
  });
  const [error, setError] = useState<string | null>(null);
  const set = (k: keyof typeof form, val: string) => setForm((f) => ({ ...f, [k]: val }));
  const save = useMutation({
    mutationFn: () => api.put("/doctor/verification/details", form),
    onSuccess: () => {
      toast.success("Details updated — checking again");
      onDone();
    },
    onError: (e) => setError(e instanceof ApiError && e.status === 422 ? "Please check the fields and try again." : e.message),
  });
  return (
    <form
      className="grid gap-3 rounded-lg border p-3 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        save.mutate();
      }}
    >
      <Field label="Full name (as registered)" htmlFor="v-name" className="sm:col-span-2">
        <Input id="v-name" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} required />
      </Field>
      <Field label="Specialty" htmlFor="v-spec">
        <NativeSelect id="v-spec" value={form.specialty} onChange={(e) => set("specialty", e.target.value)}>
          {config?.specialties.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </NativeSelect>
      </Field>
      <Field label="Hospital / clinic" htmlFor="v-org">
        <Input id="v-org" value={form.organization} onChange={(e) => set("organization", e.target.value)} required />
      </Field>
      <Field label="Medical council" htmlFor="v-council">
        <Input id="v-council" list="council-list" value={form.council} onChange={(e) => set("council", e.target.value)} required />
      </Field>
      <Field label="Registration number" htmlFor="v-reg">
        <Input id="v-reg" value={form.registration_number} onChange={(e) => set("registration_number", e.target.value)} required />
      </Field>
      <CouncilList councils={config?.councils ?? []} />
      {error && <p className="text-sm text-critical sm:col-span-2">{error}</p>}
      <Button type="submit" className="sm:col-span-2" disabled={save.isPending}>
        {save.isPending && <Loader2 className="animate-spin" />} Save and check again
      </Button>
    </form>
  );
}

export function CouncilList({ councils }: { councils: string[] }) {
  return (
    <datalist id="council-list">
      {councils.map((c) => (
        <option key={c} value={c} />
      ))}
    </datalist>
  );
}
