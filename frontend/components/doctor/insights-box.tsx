"use client";

import { useMutation } from "@tanstack/react-query";
import { Loader2, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Sparkline } from "@/components/record/sparkline";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

interface InsightRow {
  profile_id: string;
  name: string;
  age: number;
  sex: string;
  metric: string;
  slope_per_year?: number;
  sparkline?: { date: string; value: number }[];
}
interface InsightsOut {
  answer: string;
  table: { kind: string; rows: InsightRow[] };
  tools_used: { tool: string; args: Record<string, unknown>; patients: number }[];
  panel_size: number;
}

const EXAMPLES = ["Which of my patients have declining kidney function?", "Who is on metformin?", "Who has a critical safety alert?"];

export function InsightsBox() {
  const [q, setQ] = useState("");
  const ask = useMutation({ mutationFn: (question: string) => api.post<InsightsOut>("/doctor/insights", { question }) });
  const run = (question: string) => {
    setQ(question);
    ask.mutate(question);
  };
  return (
    <section className="rounded-xl border bg-card p-4">
      <p className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Sparkles className="size-4 text-primary" /> Panel insights
        <span className="font-normal text-muted-foreground">— across the patients who shared with you</span>
      </p>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) run(q.trim());
        }}
      >
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about your panel…" aria-label="Ask about your panel" />
        <Button type="submit" disabled={!q.trim() || ask.isPending}>
          {ask.isPending ? <Loader2 className="animate-spin" /> : <Search />} Ask
        </Button>
      </form>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {EXAMPLES.map((e) => (
          <button
            key={e}
            onClick={() => run(e)}
            disabled={ask.isPending}
            className="rounded-full border px-2.5 py-1 text-xs hover:border-primary/50 hover:bg-accent/40 disabled:opacity-50"
          >
            {e}
          </button>
        ))}
      </div>
      {ask.isError && <p className="mt-3 text-sm text-critical">{ask.error.message}</p>}
      {ask.data && (
        <div className="mt-4 space-y-3">
          <p className="text-sm">{ask.data.answer}</p>
          {ask.data.table.rows.length > 0 ? (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1 font-medium">Patient</th>
                  <th className="py-1 font-medium">{ask.data.table.kind}</th>
                  <th className="py-1 font-medium">Trend</th>
                </tr>
              </thead>
              <tbody>
                {ask.data.table.rows.map((r) => (
                  <tr key={r.profile_id} className="border-t">
                    <td className="py-2">
                      <Link href={`/doctor/patients/${r.profile_id}`} className="font-medium text-primary hover:underline">
                        {r.name}
                      </Link>
                      <span className="block text-xs text-muted-foreground">
                        {r.age} yrs · {r.sex}
                      </span>
                    </td>
                    <td className="py-2">
                      {r.metric}
                      {r.slope_per_year !== undefined && (
                        <span className="block text-xs text-muted-foreground">{r.slope_per_year > 0 ? "+" : ""}{r.slope_per_year} per year</span>
                      )}
                    </td>
                    <td className="py-2">{r.sparkline && <Sparkline points={r.sparkline} label={r.metric} tone={(r.slope_per_year ?? 0) < 0 ? "warning" : "neutral"} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted-foreground">No matching patients among the {ask.data.panel_size} who shared with you.</p>
          )}
          <p className="text-[11px] text-muted-foreground">
            Answered with tools over consented records only: {ask.data.tools_used.map((t) => t.tool).join(", ") || "none"}
          </p>
        </div>
      )}
    </section>
  );
}
