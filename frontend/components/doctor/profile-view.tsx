"use client";

import { BadgeCheck } from "lucide-react";

import { VerificationBanner } from "@/components/doctor/verification-banner";
import { VerificationPanel } from "@/components/doctor/verification-panel";
import { PageHeader } from "@/components/states";
import { Card, CardContent } from "@/components/ui/card";
import { fmtInstant } from "@/lib/format";
import { useMe } from "@/lib/hooks/auth";

export function DoctorProfileView() {
  const { data: me } = useMe();
  const d = me?.doctor;
  if (!d) return null;
  const rows = [
    ["Name", d.full_name],
    ["Specialty", d.specialty],
    ["Hospital / clinic", d.organization],
    ["Medical council", d.council],
    ["Registration number", d.registration_number],
    ["Email", me.email],
  ];
  return (
    <div className="max-w-2xl space-y-5">
      <PageHeader title="Professional profile" />
      <VerificationBanner doctor={d} />
      <VerificationPanel doctor={d} />
      {d.verification_status === "verified" && (
        <p className="flex items-center gap-2 text-sm text-success">
          <BadgeCheck className="size-4" /> Verified {d.verified_at ? `on ${fmtInstant(d.verified_at, "d MMM yyyy")}` : ""}
        </p>
      )}
      <Card>
        <CardContent>
          <dl className="divide-y">
            {rows.map(([k, v]) => (
              <div key={k} className="grid grid-cols-3 gap-4 py-2.5 text-sm">
                <dt className="text-muted-foreground">{k}</dt>
                <dd className="col-span-2 font-medium">{v}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
    </div>
  );
}
