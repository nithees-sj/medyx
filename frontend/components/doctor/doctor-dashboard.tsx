"use client";

import { formatDistanceToNowStrict } from "date-fns";
import { AlertOctagon, AlertTriangle, Send, Users } from "lucide-react";
import Link from "next/link";

import { InsightsBox } from "@/components/doctor/insights-box";
import { VerificationBanner } from "@/components/doctor/verification-banner";
import { Sparkline } from "@/components/record/sparkline";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/states";
import { buttonVariants } from "@/components/ui/button";
import { useMe } from "@/lib/hooks/auth";
import { useDoctorPatients } from "@/lib/hooks/doctor";

export function DoctorDashboard() {
  const { data: me } = useMe();
  const verified = me?.doctor?.verification_status === "verified";
  const patients = useDoctorPatients(verified);

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Good day, ${me?.doctor?.full_name ?? me?.name ?? ""}`}
        description={me?.doctor ? `${me.doctor.specialty} · ${me.doctor.organization}` : undefined}
        actions={
          verified ? (
            <Link href="/doctor/requests" className={buttonVariants({ variant: "outline", size: "sm" })}>
              <Send /> Request access
            </Link>
          ) : undefined
        }
      />
      {me?.doctor && <VerificationBanner doctor={me.doctor} />}
      {verified && (
        <>
          <InsightsBox />
          <section className="space-y-3">
            <h2 className="font-medium">Your patients</h2>
            {patients.isLoading ? (
              <LoadingState />
            ) : patients.isError ? (
              <ErrorState error={patients.error} onRetry={() => patients.refetch()} />
            ) : !patients.data?.length ? (
              <EmptyState
                icon={Users}
                title="No shared records yet"
                description="When a patient shares their record with you by QR or approves your request, they'll appear here."
              />
            ) : (
              <div className="overflow-x-auto rounded-xl border bg-card">
                <table className="w-full min-w-[720px] text-sm">
                  <thead className="border-b text-left text-xs text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2.5 font-medium">Patient</th>
                      <th className="px-4 py-2.5 font-medium">Alerts</th>
                      <th className="px-4 py-2.5 font-medium">eGFR</th>
                      <th className="px-4 py-2.5 font-medium">Access ends</th>
                      <th className="px-4 py-2.5 font-medium">Last activity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {patients.data.map((p) => (
                      <tr key={p.profile_id} className="border-b last:border-0 hover:bg-muted/40">
                        <td className="px-4 py-3">
                          <Link href={`/doctor/patients/${p.profile_id}`} className="font-medium text-primary hover:underline">
                            {p.name}
                          </Link>
                          <span className="block text-xs text-muted-foreground">
                            {p.age} yrs · {p.sex} · {p.healththread_id}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            {p.critical_alerts > 0 && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-critical px-2 py-0.5 text-xs font-semibold text-white">
                                <AlertOctagon className="size-3" /> {p.critical_alerts} critical
                              </span>
                            )}
                            {p.warning_alerts > 0 && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-warning px-2 py-0.5 text-xs font-semibold text-white">
                                <AlertTriangle className="size-3" /> {p.warning_alerts} warning{p.warning_alerts > 1 ? "s" : ""}
                              </span>
                            )}
                            {!p.critical_alerts && !p.warning_alerts && <span className="text-xs text-muted-foreground">None</span>}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <Sparkline
                            points={p.egfr}
                            label={`eGFR ${p.egfr.map((x) => x.value).join(" → ")}`}
                            tone={p.egfr.length > 1 && p.egfr[p.egfr.length - 1].value < p.egfr[0].value ? "warning" : "neutral"}
                          />
                        </td>
                        <td className="px-4 py-3 text-xs">{p.expires_at ? formatDistanceToNowStrict(new Date(p.expires_at)) : "—"}</td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">
                          {p.last_activity ? `${formatDistanceToNowStrict(new Date(p.last_activity))} ago` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
