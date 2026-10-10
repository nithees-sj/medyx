"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Clock, Loader2, Lock, QrCode, ShieldX } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

import { Logo } from "@/components/brand/logo";
import { ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Countdown } from "@/components/ui/countdown";
import { api } from "@/lib/api";
import { DURATIONS, type Scope, SCOPE_LABEL } from "@/lib/hooks/consents";

interface Preview {
  patient: { name: string; age: number; sex: string };
  shared_by: string | null;
  scopes: Scope[];
  can_write: boolean;
  duration_hours: number;
  claim_deadline: string | null;
  status: string;
  profile_id: string | null;
  problem: string | null;
}

export function ClaimView() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const preview = useQuery({ queryKey: ["share", token], queryFn: () => api.get<Preview>(`/share/${token}`), retry: false });
  const claim = useMutation({
    mutationFn: () => api.post<{ profile_id: string }>(`/share/${token}/claim`),
    onSuccess: (r) => {
      toast.success("Record opened");
      router.replace(`/doctor/patients/${r.profile_id}`);
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <main className="mx-auto w-full max-w-lg flex-1 space-y-5 px-4 py-10">
      <Logo />
      {preview.isLoading ? (
        <LoadingState rows={2} />
      ) : preview.isError ? (
        <ErrorState error={preview.error} />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <QrCode className="size-5 text-primary" /> Shared health record
            </CardTitle>
            <CardDescription>
              {preview.data!.shared_by ? `${preview.data!.shared_by} is sharing` : "A patient is sharing"} this record with you.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-xl font-semibold">{preview.data!.patient.name}</p>
              <p className="text-sm text-muted-foreground">
                {preview.data!.patient.age} yrs · {preview.data!.patient.sex}
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {preview.data!.scopes.map((s) => (
                <Badge key={s} variant="secondary">
                  {SCOPE_LABEL[s]}
                </Badge>
              ))}
              <Badge variant="outline">{preview.data!.can_write ? "Can add documents & prescriptions" : "Read-only"}</Badge>
            </div>
            <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Lock className="size-4" /> Access lasts {DURATIONS.find((d) => d.hours === preview.data!.duration_hours)?.label}. Every view is
              logged and visible to the patient.
            </p>
            {preview.data!.problem === "already_claimed" ? (
              <Link href={`/doctor/patients/${preview.data!.profile_id}`} className={buttonVariants({ size: "lg" })}>
                <CheckCircle2 /> Open the record
              </Link>
            ) : preview.data!.problem ? (
              <p className="flex gap-2 rounded-lg border border-critical/30 bg-critical-soft px-3 py-2 text-sm">
                <ShieldX className="size-4 shrink-0 text-critical" /> {preview.data!.problem}
              </p>
            ) : (
              <>
                {preview.data!.claim_deadline && (
                  <p className="flex items-center gap-1.5 text-sm">
                    <Clock className="size-4 text-warning" /> This code expires in <Countdown until={preview.data!.claim_deadline} />
                  </p>
                )}
                <Button size="lg" className="w-full" onClick={() => claim.mutate()} disabled={claim.isPending}>
                  {claim.isPending && <Loader2 className="animate-spin" />} Open {preview.data!.patient.name.split(" ")[0]}&apos;s record
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </main>
  );
}
