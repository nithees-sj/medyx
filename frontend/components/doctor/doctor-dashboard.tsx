"use client";

import { useQuery } from "@tanstack/react-query";
import { Users } from "lucide-react";

import { VerificationBanner } from "@/components/doctor/verification-banner";
import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/states";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks/auth";

interface PatientRow {
  profile_id: string;
  name: string;
  age: number;
  sex: string;
  healththread_id: string;
  scopes: string[];
  can_write: boolean;
  expires_at: string | null;
}

export function DoctorDashboard() {
  const { data: me } = useMe();
  const verified = me?.doctor?.verification_status === "verified";
  const patients = useQuery({
    queryKey: ["doctor-patients"],
    queryFn: () => api.get<PatientRow[]>("/doctor/patients"),
    enabled: verified,
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Good day, ${me?.doctor?.full_name ?? me?.name ?? ""}`}
        description={me?.doctor ? `${me.doctor.specialty} · ${me.doctor.organization}` : undefined}
      />
      {me?.doctor && <VerificationBanner doctor={me.doctor} />}
      {verified && (
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
            <ul className="divide-y rounded-xl border bg-card">
              {patients.data.map((p) => (
                <li key={p.profile_id} className="flex items-center justify-between px-4 py-3 text-sm">
                  <span className="font-medium">{p.name}</span>
                  <span className="text-muted-foreground">
                    {p.age} yrs · {p.healththread_id}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
