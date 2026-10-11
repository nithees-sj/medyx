"use client";

import { Activity, Bot, FileUp, LogIn, ServerCrash, ShieldAlert, Siren, Stethoscope } from "lucide-react";
import Link from "next/link";

import { ActivityList, useActivity } from "@/components/admin/activity";
import { DailyActivityChart } from "@/components/admin/charts";
import { AttentionList, Kpi, Panel, fmtNum } from "@/components/admin/ui";
import { ErrorState, LoadingState, PageHeader } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { fmtInstant } from "@/lib/format";
import { useOverview, useSharing } from "@/lib/hooks/admin";

export function AdminOverview() {
  const ov = useOverview();
  const sharing = useSharing();
  const recent = useActivity({ limit: 8 });

  if (ov.isLoading) return <LoadingState rows={6} />;
  if (ov.isError) return <ErrorState error={ov.error} onRetry={() => ov.refetch()} />;
  const { kpis, last_24h: d, attention, daily } = ov.data!;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Platform overview"
        description="Live view of what is happening across HealthThread. Patients appear only as HealthThread IDs — admins never see health records."
      />

      <section aria-label="Last 24 hours" className="space-y-2">
        <h2 className="text-sm font-medium text-muted-foreground">Last 24 hours</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Kpi icon={Activity} label="Active users" value={fmtNum(d.active_users)} hint={`${fmtNum(d.requests)} API requests`} />
          <Kpi
            icon={LogIn}
            label="Sign-ins"
            value={fmtNum(d.sign_ins)}
            hint={d.failed_sign_ins ? `${d.failed_sign_ins} failed` : "no failures"}
            tone={d.failed_sign_ins ? "warning" : "neutral"}
          />
          <Kpi icon={FileUp} label="Documents uploaded" value={fmtNum(d.uploads)} />
          <Kpi icon={Stethoscope} label="Doctor record access" value={fmtNum(d.doctor_record_access)} hint="views, chats, summaries, prescriptions" />
          <Kpi
            icon={Bot}
            label="AI calls"
            value={fmtNum(d.ai_calls)}
            hint={!d.ai_calls ? "none yet" : d.ai_failures ? `${d.ai_failures} failed or rate-limited` : "all succeeded"}
            tone={d.ai_calls && d.ai_failures / d.ai_calls >= 0.2 ? "warning" : "neutral"}
          />
          <Kpi icon={ServerCrash} label="Server errors" value={fmtNum(d.server_errors)} tone={d.server_errors ? "critical" : "neutral"} />
          <Kpi icon={ShieldAlert} label="Access denied" value={fmtNum(d.access_denied)} hint="blocked requests (deduplicated)" />
          <Kpi icon={Siren} label="Emergency card views" value={fmtNum(d.emergency_views)} tone={d.emergency_views ? "warning" : "neutral"} />
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Activity, last 14 days" className="lg:col-span-2">
          <DailyActivityChart data={daily} />
        </Panel>
        <Panel title="Needs attention">
          <AttentionList items={attention} />
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Platform totals">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
            <Stat label="Users" value={kpis.users} detail={breakdown(kpis.users_by_role)} />
            <Stat label="Doctors" value={Object.values(kpis.doctors).reduce((a, b) => a + b, 0)} detail={breakdown(kpis.doctors)} />
            <Stat label="Health profiles" value={kpis.profiles} />
            <Stat label="Documents" value={kpis.documents} detail={breakdown(kpis.documents_by_status)} />
            <Stat label="Active shares" value={kpis.active_consents} />
            <Stat label="Active safety alerts" value={kpis.active_alerts} detail={kpis.critical_alerts ? `${kpis.critical_alerts} critical` : undefined} />
          </dl>
          {Object.keys(kpis.alerts_by_type).length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {Object.entries(kpis.alerts_by_type).map(([t, n]) => (
                <Badge key={t} variant="secondary">
                  {t.replace(/_/g, " ")} · {n}
                </Badge>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Sharing & emergency access" className="lg:col-span-2">
          {sharing.data ? (
            <div className="space-y-4">
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-4">
                <Stat label="Active shares" value={sharing.data.active} detail={`${sharing.data.expiring_24h} expire within 24 h`} />
                <Stat label="Shares created (7 d)" value={sharing.data.created_7d} detail={`${sharing.data.revoked_7d} revoked`} />
                <Stat label="Emergency cards on" value={sharing.data.emergency_cards_enabled} />
                <Stat
                  label="Emergency views (7 d)"
                  value={sharing.data.emergency_views_7d}
                  detail={`${sharing.data.invalid_links_24h} invalid link attempts (24 h)`}
                />
              </dl>
              {sharing.data.recent_emergency_views.length > 0 && (
                <div>
                  <p className="mb-1 text-xs font-medium text-muted-foreground">Recent emergency card views</p>
                  <ul className="divide-y text-sm">
                    {sharing.data.recent_emergency_views.slice(0, 5).map((v) => (
                      <li key={v.at + v.profile} className="flex flex-wrap gap-x-3 py-1.5">
                        <span className="font-mono text-xs">{v.profile}</span>
                        <span className="text-muted-foreground">{fmtInstant(v.at, "d MMM, h:mm a")}</span>
                        <span className="truncate text-xs text-muted-foreground">
                          {v.ip ?? "unknown IP"} · {v.user_agent || "unknown device"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <LoadingState rows={2} />
          )}
        </Panel>
      </div>

      <Panel
        title="Latest activity"
        actions={
          <Link href="/admin/activity" className="text-sm font-medium text-primary hover:underline">
            Open activity log
          </Link>
        }
      >
        {recent.data ? <ActivityList items={recent.data.pages.flatMap((p) => p.items)} compact /> : <LoadingState rows={3} />}
      </Panel>
    </div>
  );
}

function breakdown(m: Record<string, number>): string {
  return Object.entries(m)
    .map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`)
    .join(" · ");
}

function Stat({ label, value, detail }: { label: string; value: number; detail?: string }) {
  return (
    <div>
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums">{fmtNum(value)}</dd>
      {detail && <dd className="text-xs text-muted-foreground">{detail}</dd>}
    </div>
  );
}
