"use client";

import {
  Activity,
  AlertTriangle,
  ClipboardCheck,
  FileText,
  History,
  LineChart,
  Pill,
  QrCode,
  Siren,
  Upload,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AddProfileDialog } from "@/components/patient/add-profile-dialog";
import { ALERT_TYPE_LABEL, SeverityBadge } from "@/components/record/alert-card";
import { DocumentStatus } from "@/components/record/documents-view";
import { ProfileSwitcher } from "@/components/patient/profile-switcher";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Card, CardContent } from "@/components/ui/card";
import { docTypeLabel, fmtDate } from "@/lib/format";
import { lastProfile, rememberProfile, useProfiles } from "@/lib/hooks/profiles";
import { useAlerts, useDocuments } from "@/lib/hooks/record";
import type { Profile } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PatientHome() {
  const { data: profiles, isLoading, isError, error, refetch } = useProfiles();
  // Remembered choice; falls back to the first profile if it no longer exists.
  const [selectedId, setSelectedId] = useState<string | null>(() => lastProfile());

  if (isLoading) return <LoadingState rows={4} />;
  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!profiles?.length) {
    return (
      <EmptyState
        title="No health profiles yet"
        description="Create a profile for yourself or someone you care for."
        action={<AddProfileDialog />}
      />
    );
  }
  const profile = profiles.find((p) => p.id === selectedId) ?? profiles[0];
  const select = (id: string) => {
    setSelectedId(id);
    rememberProfile(id);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ProfileSwitcher profiles={profiles} selectedId={profile.id} onSelect={select} />
        <AddProfileDialog onCreated={(p) => select(p.id)} />
      </div>
      <ProfileOverview profile={profile} />
    </div>
  );
}

function ProfileOverview({ profile: p }: { profile: Profile }) {
  const base = `/app/p/${p.id}`;
  return (
    <div className="space-y-5">
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{p.display_name}</h1>
            <p className="text-sm text-muted-foreground">
              {p.age} yrs · {p.sex === "unknown" ? "sex not recorded" : p.sex} · Blood group{" "}
              {p.blood_group === "unknown" ? "not recorded" : p.blood_group}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted-foreground">HealthThread ID</p>
            <p className="font-mono text-sm font-medium tracking-wider">{p.healththread_id}</p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          href={`${base}/alerts`}
          icon={AlertTriangle}
          label="Active alerts"
          value={p.active_alerts}
          tone={p.critical_alerts ? "critical" : p.active_alerts ? "warning" : "neutral"}
          note={p.critical_alerts ? `${p.critical_alerts} critical` : p.active_alerts ? "Review with a doctor" : "Nothing flagged"}
        />
        <StatCard
          href={`${base}/documents`}
          icon={FileText}
          label="Documents"
          value={p.documents}
          note={p.documents ? "From all hospitals" : "Upload your first report"}
        />
        <StatCard
          href={`${base}/review`}
          icon={ClipboardCheck}
          label="Needs your review"
          value={p.pending_review}
          tone={p.pending_review ? "warning" : "neutral"}
          note={p.pending_review ? "Check what we read" : "All confirmed"}
        />
      </div>

      <HomeAlerts profileId={p.id} base={base} />

      {p.pending_review > 0 && (
        <Link
          href={`${base}/review`}
          className="flex items-center gap-3 rounded-xl border border-warning/40 bg-warning-soft p-4 text-sm focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <ClipboardCheck className="size-5 shrink-0 text-warning" />
          <span>
            <span className="font-medium">{p.pending_review} item{p.pending_review > 1 ? "s" : ""} to check.</span> We weren&apos;t fully
            sure what a document said. Confirm before it goes into the record.
          </span>
        </Link>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground">Quick actions</h2>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          <Action href={`${base}/upload`} icon={Upload} label="Upload" primary />
          <Action href={`${base}/sharing`} icon={QrCode} label="Share" />
          <Action href={`${base}/emergency`} icon={Siren} label="Emergency card" />
          <Action href={`${base}/timeline`} icon={Activity} label="Timeline" />
          <Action href={`${base}/trends`} icon={LineChart} label="Lab trends" />
          <Action href={`${base}/medications`} icon={Pill} label="Medicines" />
          <Action href={`${base}/documents`} icon={FileText} label="Documents" />
          <Action href={`${base}/access-log`} icon={History} label="Access log" />
        </div>
      </section>

      <RecentDocuments profileId={p.id} base={base} />
    </div>
  );
}

function RecentDocuments({ profileId, base }: { profileId: string; base: string }) {
  const { data } = useDocuments(profileId);
  if (!data?.length) return null;
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-muted-foreground">Recent documents</h2>
        <Link href={`${base}/documents`} className="text-sm text-primary hover:underline">
          See all {data.length}
        </Link>
      </div>
      <ul className="divide-y rounded-xl border bg-card">
        {data.slice(0, 4).map((d) => (
          <li key={d.id} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
            <span className="min-w-0">
              <span className="block truncate font-medium">
                {docTypeLabel(d.document_type)} · {d.source_org_name ?? d.original_filename}
              </span>
              <span className="text-xs text-muted-foreground">
                {d.label} · {fmtDate(d.document_date ?? d.created_at)}
              </span>
            </span>
            <DocumentStatus doc={d} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function StatCard({
  href,
  icon: Icon,
  label,
  value,
  note,
  tone = "neutral",
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  note: string;
  tone?: "neutral" | "warning" | "critical";
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-3 rounded-xl border bg-card p-4 transition-colors hover:border-primary/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
        tone === "critical" && "border-critical/40 bg-critical-soft",
        tone === "warning" && "border-warning/40 bg-warning-soft",
      )}
    >
      <Icon
        className={cn(
          "size-6 shrink-0",
          tone === "critical" ? "text-critical" : tone === "warning" ? "text-warning" : "text-primary",
        )}
      />
      <div className="min-w-0">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="text-2xl leading-tight font-semibold">{value}</p>
        <p className="truncate text-xs text-muted-foreground">{note}</p>
      </div>
    </Link>
  );
}

function Action({
  href,
  icon: Icon,
  label,
  primary,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex flex-col items-center gap-1.5 rounded-xl border p-3 text-center text-xs font-medium transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none sm:text-sm",
        primary ? "border-primary bg-primary text-primary-foreground hover:bg-primary/90" : "bg-card hover:bg-muted",
      )}
    >
      <Icon className="size-5" />
      {label}
    </Link>
  );
}

function HomeAlerts({ profileId, base }: { profileId: string; base: string }) {
  const { data } = useAlerts(profileId);
  if (!data?.length) return null;
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-muted-foreground">Needs attention</h2>
        <Link href={`${base}/alerts`} className="text-sm text-primary hover:underline">
          All alerts
        </Link>
      </div>
      <ul className="space-y-2">
        {data.slice(0, 4).map((a) => (
          <li key={a.id}>
            <Link
              href={`${base}/alerts`}
              className={cn(
                "flex flex-col gap-1.5 rounded-xl border bg-card p-3 transition-colors hover:border-primary/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none sm:flex-row sm:items-center sm:gap-3",
                a.severity === "critical" ? "border-critical/40" : "border-warning/40",
              )}
            >
              <span className="flex items-center gap-2">
                <SeverityBadge severity={a.severity} />
                <span className="text-xs text-muted-foreground sm:hidden">{ALERT_TYPE_LABEL[a.type]}</span>
              </span>
              <span className="min-w-0 text-sm font-medium sm:truncate">{a.title}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
