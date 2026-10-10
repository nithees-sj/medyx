"use client";

import { Eye, FileUp, History, KeyRound, MessageSquare, Pill, Siren, Stethoscope, Download, ClipboardCheck } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { fmtInstant } from "@/lib/format";
import { scopesText, useAudit, type AuditRow } from "@/lib/hooks/consents";
import { cn } from "@/lib/utils";

const ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  view: Eye,
  upload: FileUp,
  prescribe: Pill,
  chat: MessageSquare,
  summary: Stethoscope,
  export: Download,
  emergency_view: Siren,
  consent_change: KeyRound,
  alert_review: ClipboardCheck,
};

const SECTION: Record<string, string> = {
  timeline: "the timeline",
  trends: "lab trends",
  medications: "medicines",
  alerts: "safety alerts",
  workspace: "the record",
  summary: "a summary",
};

const CONSENT_EVENT: Record<string, string> = {
  share_created: "created a QR share",
  share_claimed: "opened the shared record (QR)",
  access_requested: "requested access",
  request_approved: "approved access",
  request_denied: "declined an access request",
  revoked: "revoked access",
};

const ITEM_LABEL: Record<string, string> = {
  AllergyIntolerance: "allergy",
  MedicationRequest: "medicine",
  Condition: "condition",
  Observation: "lab result",
  Vital: "vital sign",
};

function sentence(e: AuditRow): string {
  const d = e.details as Record<string, string>;
  switch (e.action) {
    case "view":
      return `viewed ${e.scopes.length ? scopesText(e.scopes) : SECTION[d.section] ?? "the record"}${d.section ? ` (${SECTION[d.section] ?? d.section})` : ""}`;
    case "consent_change":
      return CONSENT_EVENT[d.event] ?? "changed sharing";
    case "upload":
      return d.review ? `${d.review === "reject" ? "removed" : "confirmed"} an extracted ${ITEM_LABEL[d.item] ?? "item"}` : d.medication_stopped ? "marked a medicine as stopped" : `uploaded ${d.document ?? "a document"}`;
    case "emergency_view":
      return "opened the emergency card";
    case "prescribe":
      return `prescribed ${d.medicine ?? "a medicine"}`;
    case "chat":
      return "asked the copilot about the record";
    case "summary":
      return `opened a ${d.specialty ?? ""} summary`.replace("  ", " ");
    case "export":
      return "exported the full record (FHIR)";
    case "alert_review":
      return `marked “${d.alert}” as ${String(d.status).replace("_", " — ")}`;
    default:
      return e.verb;
  }
}

export function AccessLogView({ profileId }: { profileId: string }) {
  const { data, isLoading, isError, error, refetch } = useAudit(profileId);
  if (isLoading) return <LoadingState rows={5} />;
  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data?.length)
    return <EmptyState icon={History} title="No activity yet" description="Every time a doctor or an emergency responder opens this record, it appears here." />;
  const byDay = data.reduce<Record<string, AuditRow[]>>((acc, e) => {
    (acc[fmtInstant(e.created_at, "EEEE, d MMM yyyy")] ??= []).push(e);
    return acc;
  }, {});
  return (
    <div className="space-y-5">
      <p className="text-sm text-muted-foreground">Every view by a doctor, every emergency scan and every sharing change. Times are shown in IST.</p>
      {Object.entries(byDay).map(([day, events]) => (
        <section key={day}>
          <h2 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{day}</h2>
          <ol className="relative space-y-3 border-l pl-5">
            {events.map((e) => {
              const Icon = ICON[e.action] ?? Eye;
              const emergency = e.action === "emergency_view";
              return (
                <li key={e.id} className="relative">
                  <span
                    className={cn(
                      "absolute top-0.5 -left-[31px] flex size-6 items-center justify-center rounded-full border bg-card",
                      emergency && "border-critical bg-critical-soft",
                    )}
                  >
                    <Icon className={cn("size-3.5", emergency ? "text-critical" : "text-primary")} />
                  </span>
                  <p className="text-sm">
                    <span className="font-medium">{e.actor_is_owner ? "You" : e.actor}</span> {sentence(e)}
                    <span className="text-muted-foreground"> — {fmtInstant(e.created_at, "h:mm a")}</span>
                  </p>
                  {emergency && e.ip && <p className="text-xs text-muted-foreground">From {e.ip}</p>}
                </li>
              );
            })}
          </ol>
        </section>
      ))}
    </div>
  );
}
