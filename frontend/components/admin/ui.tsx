"use client";

import { AlertOctagon, AlertTriangle, CheckCircle2, CircleDashed, CircleSlash, Info, XCircle } from "lucide-react";
import Link from "next/link";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { CheckRow } from "@/lib/hooks/admin";
import { cn } from "@/lib/utils";

export function Kpi({
  label,
  value,
  hint,
  tone = "neutral",
  icon: Icon,
}: {
  label: string;
  value: number | string | undefined;
  hint?: React.ReactNode;
  tone?: "neutral" | "warning" | "critical" | "success";
  icon?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-card p-4",
        tone === "warning" && "border-warning/40 bg-warning-soft",
        tone === "critical" && "border-critical/40 bg-critical-soft",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">{label}</p>
        {Icon && <Icon className="size-4 text-muted-foreground" />}
      </div>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value ?? "–"}</p>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function Panel({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <CardTitle className="text-base">{title}</CardTitle>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function StatusPill({ ok, label }: { ok: boolean | null | undefined; label: string }) {
  const Icon = ok ? CheckCircle2 : ok === false ? XCircle : CircleDashed;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
        ok ? "border-success/40 bg-success-soft" : ok === false ? "border-critical/40 bg-critical-soft" : "bg-muted",
      )}
    >
      <Icon className={cn("size-3.5", ok ? "text-success" : ok === false ? "text-critical" : "text-muted-foreground")} />
      {label}
    </span>
  );
}

const CHECK_META: Record<CheckRow["status"], { label: string; icon: React.ComponentType<{ className?: string }>; cls: string }> = {
  passed: { label: "Passed", icon: CheckCircle2, cls: "text-success" },
  warning: { label: "Check", icon: AlertTriangle, cls: "text-warning" },
  failed: { label: "Failed", icon: XCircle, cls: "text-critical" },
  missing: { label: "No evidence", icon: CircleDashed, cls: "text-muted-foreground" },
  not_configured: { label: "Not configured", icon: CircleSlash, cls: "text-muted-foreground" },
  error: { label: "Error", icon: AlertOctagon, cls: "text-warning" },
};

export const CHECK_TITLE: Record<CheckRow["kind"], string> = {
  format: "Details",
  duplicate: "Unique registration",
  registry: "Medical register",
  identity: "Work identity",
  document: "Certificate",
};

export function CheckStatus({ status }: { status: CheckRow["status"] }) {
  const m = CHECK_META[status] ?? CHECK_META.missing;
  return (
    <span className="inline-flex shrink-0 items-center gap-1 text-xs font-medium">
      <m.icon className={cn("size-4", m.cls)} />
      {m.label}
    </span>
  );
}

export function RiskBadge({ risk }: { risk: "low" | "medium" | "high" | null }) {
  if (!risk) return <span className="rounded-full bg-muted px-2 py-0.5 text-xs">Not checked yet</span>;
  const cls = {
    low: "border-success/40 bg-success-soft",
    medium: "border-warning/40 bg-warning-soft",
    high: "border-critical/40 bg-critical-soft",
  }[risk];
  const text = { low: "Strong evidence", medium: "Incomplete evidence", high: "Conflicting evidence" }[risk];
  return <span className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", cls)}>{text}</span>;
}

export function AttentionList({
  items,
}: {
  items: { kind: string; severity: "critical" | "warning" | "info"; title: string; count: number; link: string }[];
}) {
  if (!items.length)
    return (
      <p className="flex items-center gap-2 text-sm text-success">
        <CheckCircle2 className="size-4" /> Nothing needs attention right now.
      </p>
    );
  return (
    <ul className="divide-y">
      {items.map((a) => {
        const Icon = a.severity === "critical" ? AlertOctagon : a.severity === "warning" ? AlertTriangle : Info;
        return (
          <li key={a.kind}>
            <Link href={a.link} className="flex items-center gap-3 py-2.5 text-sm hover:text-primary">
              <Icon
                className={cn(
                  "size-4 shrink-0",
                  a.severity === "critical" ? "text-critical" : a.severity === "warning" ? "text-warning" : "text-primary",
                )}
              />
              <span className="flex-1">{a.title}</span>
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold tabular-nums">{a.count}</span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  return ms >= 1000 ? `${(ms / 1000).toFixed(ms >= 10_000 ? 0 : 1)} s` : `${ms} ms`;
}

export function fmtNum(n: number | null | undefined): string {
  return n == null ? "—" : n.toLocaleString("en-IN");
}

export function pct(part: number, whole: number): string {
  return whole ? `${Math.round((part / whole) * 100)}%` : "—";
}
