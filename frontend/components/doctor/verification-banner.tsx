import { Clock, ShieldOff, XCircle } from "lucide-react";

import type { DoctorInfo } from "@/lib/types";

export function VerificationBanner({ doctor }: { doctor: DoctorInfo }) {
  const s = doctor.verification_status;
  if (s === "verified") return null;
  const blocked = s === "rejected" || s === "suspended";
  const Icon = s === "suspended" ? ShieldOff : s === "rejected" ? XCircle : Clock;
  const title = { pending: "Awaiting verification", rejected: "Verification was not approved", suspended: "Your account is suspended" }[s];
  const body =
    s === "pending"
      ? `We're checking your registration (${doctor.council} · ${doctor.registration_number}). You won't see any patient records until you're verified.`
      : s === "suspended"
        ? `${doctor.review_note ?? "Your access is paused."} Your patient shares have ended. Contact the HealthThread team.`
        : `${doctor.review_note ?? "Your details couldn't be confirmed."} You can correct your details below and we'll check again.`;
  return (
    <div
      role="status"
      className={
        blocked
          ? "flex gap-3 rounded-xl border border-critical/40 bg-critical-soft p-4"
          : "flex gap-3 rounded-xl border border-warning/40 bg-warning-soft p-4"
      }
    >
      <Icon className={blocked ? "size-5 shrink-0 text-critical" : "size-5 shrink-0 text-warning"} />
      <div className="space-y-1 text-sm">
        <p className="font-medium">{title}</p>
        <p className="text-muted-foreground">{body}</p>
      </div>
    </div>
  );
}
