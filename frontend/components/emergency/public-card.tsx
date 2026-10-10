"use client";

import { useQuery } from "@tanstack/react-query";
import { ShieldX, Siren } from "lucide-react";
import { useParams } from "next/navigation";

import { Logo } from "@/components/brand/logo";
import { EmergencyCardView, type EmergencyData } from "@/components/emergency/card-preview";
import { LoadingState } from "@/components/states";
import { api } from "@/lib/api";
import { fmtInstant } from "@/lib/format";

export function PublicEmergencyCard() {
  const { token } = useParams<{ token: string }>();
  const q = useQuery({
    queryKey: ["emergency-public", token],
    queryFn: () => api.get<EmergencyData>(`/emergency/${token}`),
    retry: false,
    staleTime: Infinity,
  });
  return (
    <main className="mx-auto w-full max-w-md flex-1 space-y-4 px-4 py-6">
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-2 text-sm font-semibold tracking-wide text-critical uppercase">
          <Siren className="size-5" /> Emergency medical information
        </span>
        <Logo compact />
      </div>
      {q.isLoading ? (
        <LoadingState rows={4} />
      ) : q.isError ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border p-8 text-center">
          <ShieldX className="size-8 text-muted-foreground" />
          <p className="font-medium">This emergency card isn&apos;t active</p>
          <p className="text-sm text-muted-foreground">It may have been replaced or turned off by its owner.</p>
        </div>
      ) : (
        <>
          <EmergencyCardView data={q.data!} />
          <p className="text-center text-xs text-muted-foreground">
            HealthThread ID {q.data!.healththread_id}
            {q.data!.last_updated ? ` · record updated ${fmtInstant(q.data!.last_updated, "d MMM yyyy")}` : ""}
            <br />
            The owner has been notified that this card was opened.
          </p>
        </>
      )}
    </main>
  );
}
