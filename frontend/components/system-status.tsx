"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

type Health = { status: string; database: boolean; fhir: boolean; fhir_version: string | null };

function Dot({ ok, label }: { ok: boolean | undefined; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={cn(
          "size-2 rounded-full",
          ok === undefined ? "bg-muted-foreground/40" : ok ? "bg-success" : "bg-critical",
        )}
      />
      {label}
    </span>
  );
}

export function SystemStatus() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<Health>("/health"),
    refetchInterval: 30_000,
  });
  return (
    <div
      className="inline-flex flex-wrap items-center gap-3 rounded-full border bg-card px-3 py-1 text-xs text-muted-foreground"
      aria-live="polite"
    >
      {isLoading ? (
        <span>Checking services…</span>
      ) : isError ? (
        <span className="text-critical">Backend unreachable</span>
      ) : (
        <>
          <Dot ok={data?.status === "ok"} label={`API ${data?.status}`} />
          <Dot ok={data?.database} label="Database" />
          <Dot ok={data?.fhir} label={`FHIR ${data?.fhir_version ?? ""}`} />
        </>
      )}
    </div>
  );
}
