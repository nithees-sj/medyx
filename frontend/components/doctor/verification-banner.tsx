import { Clock, XCircle } from "lucide-react";

import type { DoctorInfo } from "@/lib/types";

export function VerificationBanner({ doctor }: { doctor: DoctorInfo }) {
  if (doctor.verification_status === "verified") return null;
  const rejected = doctor.verification_status === "rejected";
  return (
    <div
      role="status"
      className={
        rejected
          ? "flex gap-3 rounded-xl border border-critical/40 bg-critical-soft p-4"
          : "flex gap-3 rounded-xl border border-warning/40 bg-warning-soft p-4"
      }
    >
      {rejected ? <XCircle className="size-5 shrink-0 text-critical" /> : <Clock className="size-5 shrink-0 text-warning" />}
      <div className="space-y-1 text-sm">
        <p className="font-medium">{rejected ? "Verification was not approved" : "Awaiting verification"}</p>
        <p className="text-muted-foreground">
          {rejected
            ? doctor.review_note || "Contact the HealthThread team to resubmit your details."
            : `An admin is checking your registration (${doctor.council} · ${doctor.registration_number}). You won't see any patient records until you're verified.`}
        </p>
      </div>
    </div>
  );
}
