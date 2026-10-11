"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RotateCw } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { TrafficChart } from "@/components/admin/charts";
import { Kpi, Panel, StatusPill, fmtMs, fmtNum, pct } from "@/components/admin/ui";
import { ErrorState, LoadingState, PageHeader } from "@/components/states";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { fmtInstant } from "@/lib/format";
import { type AIGroup, useAIMetrics, useHealth, usePipeline, useRequestMetrics } from "@/lib/hooks/admin";
import { cn } from "@/lib/utils";

const WINDOWS = [
  { hours: 24, label: "24 hours" },
  { hours: 168, label: "7 days" },
];

const PURPOSE_LABEL: Record<string, string> = {
  extract: "Document extraction",
  alert_explain: "Alert explanations",
  chat: "Copilot chat",
  summary: "Specialty summary",
  insights: "Panel insights",
  explain: "Patient explainer",
  verify_certificate: "Certificate reading",
};

export function SystemView() {
  const [hours, setHours] = useState(24);
  return (
    <div className="space-y-6">
      <PageHeader
        title="System"
        description="Service health, background jobs, the document pipeline, API traffic and AI usage. Only metadata is recorded — never request bodies, prompts or answers."
        actions={
          <div className="flex gap-1" role="group" aria-label="Time window">
            {WINDOWS.map((w) => (
              <Button key={w.hours} size="sm" variant={hours === w.hours ? "default" : "outline"} onClick={() => setHours(w.hours)}>
                {w.label}
              </Button>
            ))}
          </div>
        }
      />
      <HealthPanel />
      <PipelinePanel />
      <TrafficPanel hours={hours} />
      <AIPanel hours={hours} />
    </div>
  );
}

function HealthPanel() {
  const h = useHealth();
  if (h.isLoading) return <LoadingState rows={2} />;
  if (h.isError) return <ErrorState error={h.error} onRetry={() => h.refetch()} />;
  const d = h.data!;
  const deps = d.dependencies;
  return (
    <Panel
      title="Health"
      description={`API up for ${uptime(d.uptime_seconds)} (since ${fmtInstant(d.started_at, "d MMM, h:mm a")})${d.demo_mode ? " · demo mode" : ""}`}
    >
      <div className="flex flex-wrap gap-2">
        <StatusPill ok={deps.database.ok} label="Postgres" />
        <StatusPill ok={deps.fhir.ok} label={`HAPI FHIR ${deps.fhir.version ?? ""}`} />
        <StatusPill ok={deps.ai.ok} label={`Gemini · ${deps.ai.model}${deps.ai.fallback_model ? ` → ${deps.ai.fallback_model}` : ""}`} />
        <StatusPill ok={deps.registry.configured ? true : null} label={deps.registry.configured ? "Medical register connected" : "Medical register not connected"} />
        <StatusPill ok={d.ingest_worker.workers_alive > 0} label={`${d.ingest_worker.workers_alive} ingest workers · ${d.ingest_worker.queue_depth} queued`} />
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Background job</th>
              <th className="py-1.5 pr-3 font-medium">Every</th>
              <th className="py-1.5 pr-3 font-medium">Last run</th>
              <th className="py-1.5 pr-3 font-medium">Status</th>
              <th className="py-1.5 font-medium">Result</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {d.jobs.map((j) => (
              <tr key={j.name}>
                <td className="py-1.5 pr-3 font-medium">{j.name}</td>
                <td className="py-1.5 pr-3 text-muted-foreground">{j.interval_seconds ? every(j.interval_seconds) : "—"}</td>
                <td className="py-1.5 pr-3 text-muted-foreground">{j.last_run ? fmtInstant(j.last_run, "d MMM, h:mm:ss a") : "not yet"}</td>
                <td className="py-1.5 pr-3">
                  <StatusPill ok={j.ok} label={j.ok ? "OK" : j.ok === false ? "Failed" : "Waiting"} />
                </td>
                <td className={cn("py-1.5 text-xs", j.error ? "text-critical" : "text-muted-foreground")}>{j.error ?? j.result ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function PipelinePanel() {
  const p = usePipeline();
  const qc = useQueryClient();
  const retry = useMutation({
    mutationFn: (id: string) => api.post(`/admin/documents/${id}/retry`),
    onSuccess: () => {
      toast.success("Queued for another try");
      qc.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (e) => toast.error(e.message),
  });
  if (!p.data) return p.isError ? <ErrorState error={p.error} onRetry={() => p.refetch()} /> : <LoadingState rows={2} />;
  const d = p.data;
  const total = Object.values(d.by_status).reduce((a, b) => a + b, 0);
  return (
    <Panel title="Document pipeline" description="Upload → AI extraction → normalisation → merge → FHIR → safety checks. Patients shown by HealthThread ID.">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Kpi label="Queued now" value={d.queue_depth} tone={d.queue_depth > 10 ? "warning" : "neutral"} />
        <Kpi label="Processed" value={fmtNum((d.by_status.done ?? 0) + (d.by_status.needs_review ?? 0))} hint={`of ${fmtNum(total)} uploaded`} />
        <Kpi label="Waiting for patient review" value={fmtNum(d.by_status.needs_review ?? 0)} />
        <Kpi label="Failed" value={fmtNum(d.by_status.failed ?? 0)} tone={d.by_status.failed ? "warning" : "neutral"} />
        <Kpi label="Avg processing time" value={d.avg_processing_seconds_24h ? `${d.avg_processing_seconds_24h} s` : "—"} hint="last 24 h, includes AI queueing" />
      </div>
      {d.in_flight.length > 0 && (
        <div className="mt-4">
          <p className="mb-1 text-xs font-medium text-muted-foreground">In progress</p>
          <ul className="flex flex-wrap gap-2 text-xs">
            {d.in_flight.map((f) => (
              <li key={f.profile + f.label} className="rounded-full border px-2 py-1">
                <span className="font-mono">{f.profile}</span> {f.label} · {f.stage}
              </li>
            ))}
          </ul>
        </div>
      )}
      {d.failed.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr>
                <th className="py-1.5 pr-3 font-medium">Document</th>
                <th className="py-1.5 pr-3 font-medium">Failed at</th>
                <th className="py-1.5 pr-3 font-medium">Reason</th>
                <th className="py-1.5" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {d.failed.map((f) => (
                <tr key={f.id}>
                  <td className="py-1.5 pr-3">
                    <span className="font-mono text-xs">{f.profile}</span> {f.label}
                    <span className="block text-xs text-muted-foreground">uploaded by {f.uploader_role}</span>
                  </td>
                  <td className="py-1.5 pr-3 text-muted-foreground">{fmtInstant(f.failed_at, "d MMM, h:mm a")}</td>
                  <td className="py-1.5 pr-3 text-xs">{f.error}</td>
                  <td className="py-1.5 text-right">
                    <Button size="xs" variant="outline" onClick={() => retry.mutate(f.id)} disabled={retry.isPending}>
                      <RotateCw /> Retry
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function TrafficPanel({ hours }: { hours: number }) {
  const m = useRequestMetrics(hours);
  if (!m.data) return m.isError ? <ErrorState error={m.error} onRetry={() => m.refetch()} /> : <LoadingState rows={3} />;
  const d = m.data;
  return (
    <Panel title="API traffic" description="Every /api request: route, status and latency (no bodies).">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Kpi label="Requests" value={fmtNum(d.totals.requests)} />
        <Kpi label="Client errors (4xx)" value={fmtNum(d.totals.client_errors)} hint={pct(d.totals.client_errors, d.totals.requests)} />
        <Kpi
          label="Server errors (5xx)"
          value={fmtNum(d.totals.server_errors)}
          hint={pct(d.totals.server_errors, d.totals.requests)}
          tone={d.totals.server_errors ? "critical" : "neutral"}
        />
        <Kpi label="Median latency" value={fmtMs(d.totals.p50_ms)} />
        <Kpi label="p95 latency" value={fmtMs(d.totals.p95_ms)} hint="includes streamed AI answers" />
      </div>
      <div className="mt-4">
        <TrafficChart data={d.series} hourly={hours <= 72} />
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Route</th>
              <th className="py-1.5 pr-3 text-right font-medium">Requests</th>
              <th className="py-1.5 pr-3 text-right font-medium">4xx</th>
              <th className="py-1.5 pr-3 text-right font-medium">5xx</th>
              <th className="py-1.5 pr-3 text-right font-medium">p50</th>
              <th className="py-1.5 pr-3 text-right font-medium">p95</th>
              <th className="py-1.5 text-right font-medium">max</th>
            </tr>
          </thead>
          <tbody className="divide-y tabular-nums">
            {d.routes.map((r) => (
              <tr key={r.method + r.route}>
                <td className="py-1.5 pr-3 font-mono text-xs">
                  <span className="text-muted-foreground">{r.method}</span> {r.route}
                </td>
                <td className="py-1.5 pr-3 text-right">{fmtNum(r.requests)}</td>
                <td className="py-1.5 pr-3 text-right text-muted-foreground">{r.client_errors || ""}</td>
                <td className={cn("py-1.5 pr-3 text-right", r.server_errors && "font-semibold text-critical")}>{r.server_errors || ""}</td>
                <td className="py-1.5 pr-3 text-right">{fmtMs(r.p50_ms)}</td>
                <td className="py-1.5 pr-3 text-right">{fmtMs(r.p95_ms)}</td>
                <td className="py-1.5 text-right text-muted-foreground">{fmtMs(r.max_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {d.recent_errors.length > 0 && (
        <div className="mt-4">
          <p className="mb-1 text-xs font-medium text-muted-foreground">Recent server errors</p>
          <ul className="divide-y text-sm">
            {d.recent_errors.map((e, i) => (
              <li key={e.at + i} className="flex flex-wrap gap-x-3 py-1.5">
                <span className="text-muted-foreground">{fmtInstant(e.at, "d MMM, h:mm:ss a")}</span>
                <span className="font-mono text-xs">
                  {e.method} {e.route}
                </span>
                <span className="font-semibold text-critical">{e.status}</span>
                <span className="text-xs text-muted-foreground">
                  {e.error ?? ""} {e.role ? `· ${e.role}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  );
}

function AIPanel({ hours }: { hours: number }) {
  const m = useAIMetrics(hours);
  if (!m.data) return m.isError ? <ErrorState error={m.error} onRetry={() => m.refetch()} /> : <LoadingState rows={3} />;
  const d = m.data;
  const c = d.config;
  return (
    <Panel
      title="AI usage"
      description={`${c.model}${c.fallback_model ? `, falling back to ${c.fallback_model} when its quota runs out` : ""}. Purpose, model, latency and token counts only — never prompts or answers.`}
    >
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Kpi label="Calls" value={fmtNum(d.totals.calls)} />
        <Kpi
          label="Failed"
          value={fmtNum(d.totals.failures)}
          hint={d.totals.calls ? `${pct(d.totals.failures, d.totals.calls)} · ${d.totals.rate_limited} rate-limited` : "no calls yet"}
          tone={d.totals.calls && d.totals.failures / d.totals.calls >= 0.2 ? "warning" : "neutral"}
        />
        <Kpi label="Avg latency (ok)" value={fmtMs(d.totals.avg_ms)} />
        <Kpi label="Tokens in / out" value={`${compact(d.totals.input_tokens)} / ${compact(d.totals.output_tokens)}`} />
        <Kpi
          label="Quota in use now"
          value={`${c.calls_last_minute} / ${c.requests_per_minute}`}
          hint="calls in the last minute vs. AI_REQUESTS_PER_MINUTE"
          tone={c.calls_last_minute >= c.requests_per_minute ? "warning" : "neutral"}
        />
      </div>
      {d.totals.calls === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">No AI calls in this window.</p>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <GroupTable title="By feature" rows={d.by_purpose} label={(k) => PURPOSE_LABEL[k] ?? k} />
          <GroupTable title="By model" rows={d.by_model} label={(k) => k} />
        </div>
      )}
      <div className={cn("mt-4 overflow-x-auto", !d.recent.length && "hidden")}>
        <p className="mb-1 text-xs font-medium text-muted-foreground">Latest calls</p>
        <table className="w-full text-sm">
          <tbody className="divide-y tabular-nums">
            {d.recent.slice(0, 15).map((r, i) => (
              <tr key={r.at + i}>
                <td className="py-1 pr-3 text-muted-foreground">{fmtInstant(r.at, "h:mm:ss a")}</td>
                <td className="py-1 pr-3">{PURPOSE_LABEL[r.purpose] ?? r.purpose}</td>
                <td className="py-1 pr-3 font-mono text-xs">{r.model}</td>
                <td className="py-1 pr-3">
                  <StatusPill ok={r.ok} label={r.ok ? "OK" : (r.error ?? "Failed")} />
                </td>
                <td className="py-1 pr-3 text-right">{fmtMs(r.ms)}</td>
                <td className="py-1 text-right text-xs text-muted-foreground">
                  {r.input_tokens != null ? `${compact(r.input_tokens)} → ${compact(r.output_tokens ?? 0)}` : ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function GroupTable({ title, rows, label }: { title: string; rows: AIGroup[]; label: (k: string) => string }) {
  return (
    <div className="overflow-x-auto">
      <p className="mb-1 text-xs font-medium text-muted-foreground">{title}</p>
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted-foreground">
          <tr>
            <th className="py-1 pr-3 font-medium" />
            <th className="py-1 pr-3 text-right font-medium">Calls</th>
            <th className="py-1 pr-3 text-right font-medium">Failed</th>
            <th className="py-1 pr-3 text-right font-medium">Avg</th>
            <th className="py-1 text-right font-medium">Tokens in/out</th>
          </tr>
        </thead>
        <tbody className="divide-y tabular-nums">
          {rows.map((r) => (
            <tr key={r.key}>
              <td className="py-1 pr-3">{label(r.key)}</td>
              <td className="py-1 pr-3 text-right">{fmtNum(r.calls)}</td>
              <td className={cn("py-1 pr-3 text-right", r.failures && "text-warning")}>{r.failures || ""}</td>
              <td className="py-1 pr-3 text-right">{fmtMs(r.avg_ms)}</td>
              <td className="py-1 text-right text-muted-foreground">
                {compact(r.input_tokens)} / {compact(r.output_tokens)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function compact(n: number): string {
  return n >= 1_000_000 ? `${(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

function every(s: number): string {
  return s >= 3600 ? `${s / 3600} h` : s >= 60 ? `${s / 60} min` : `${s} s`;
}

function uptime(s: number): string {
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return d ? `${d} d ${h} h` : h ? `${h} h ${m} min` : `${m} min`;
}
