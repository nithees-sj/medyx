"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowRight, ArrowUpRight, Dot, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";

import { CitationChip } from "@/components/copilot/cited-text";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { useAuthConfig } from "@/lib/hooks/auth";
import type { Citation } from "@/lib/hooks/doctor";

interface SummaryLine {
  text: string;
  citations: Citation[];
  uncited: boolean;
  trend?: "up" | "down" | "stable" | "single";
}
interface SummaryOut {
  specialty: string;
  cached: boolean;
  sections: Record<"key_problems" | "current_medications" | "relevant_labs" | "active_alerts" | "open_questions", SummaryLine[]>;
}

const SECTIONS: [keyof SummaryOut["sections"], string][] = [
  ["key_problems", "Key problems"],
  ["current_medications", "Current medications"],
  ["relevant_labs", "Relevant labs"],
  ["active_alerts", "Active alerts"],
  ["open_questions", "Open questions for this visit"],
];

const TREND = { up: ArrowUpRight, down: ArrowDownRight, stable: ArrowRight, single: Dot };

export function SummaryTab({ profileId, defaultSpecialty }: { profileId: string; defaultSpecialty: string }) {
  const [specialty, setSpecialty] = useState(defaultSpecialty);
  const specialties = useAuthConfig().data?.specialties ?? [defaultSpecialty];
  const q = useQuery({
    queryKey: ["summary", profileId, specialty],
    queryFn: () => api.get<SummaryOut>(`/profiles/${profileId}/summary?specialty=${encodeURIComponent(specialty)}`),
    staleTime: 5 * 60_000,
    retry: false,
  });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="w-64">
          <NativeSelect aria-label="Specialty" value={specialty} onChange={(e) => setSpecialty(e.target.value)}>
            {specialties.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </NativeSelect>
        </div>
        <Button variant="ghost" size="sm" onClick={() => q.refetch()} disabled={q.isFetching}>
          {q.isFetching ? <Loader2 className="animate-spin" /> : <RefreshCw />} Refresh
        </Button>
        {q.data?.cached && <span className="text-xs text-muted-foreground">Up to date with the latest record</span>}
      </div>
      {q.isLoading ? (
        <div className="space-y-3" aria-busy="true">
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Writing a {specialty.toLowerCase()} summary from the record…
          </p>
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : (
        SECTIONS.map(([key, title]) => (
          <section key={key} className="rounded-xl border bg-card p-4">
            <h3 className="mb-2 text-sm font-semibold">{title}</h3>
            {q.data!.sections[key].length ? (
              <ul className="space-y-2">
                {q.data!.sections[key].map((line, i) => {
                  const Icon = line.trend ? TREND[line.trend] : null;
                  return (
                    <li key={i} className="flex gap-2 text-sm leading-relaxed">
                      {Icon ? <Icon className="mt-0.5 size-4 shrink-0 text-primary" /> : <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground" />}
                      <span>
                        {line.text}{" "}
                        {line.citations.map((c) => (
                          <CitationChip key={c.key} c={c} />
                        ))}
                        {line.uncited && <span className="text-[11px] text-warning"> (no source cited)</span>}
                      </span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Nothing in the shared record.</p>
            )}
          </section>
        ))
      )}
    </div>
  );
}
