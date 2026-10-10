"use client";

import { AlertOctagon, AlertTriangle, CheckCircle2, FileText, Info, Sparkles } from "lucide-react";

import { OrgDot } from "@/components/record/org-chip";
import { useDocumentViewer } from "@/components/record/viewer-context";
import { Badge } from "@/components/ui/badge";
import { fmtDate } from "@/lib/format";
import { orgColor } from "@/lib/hooks/record";
import type { AlertRow, OrgColors } from "@/lib/record-types";
import { cn } from "@/lib/utils";

export const ALERT_TYPE_LABEL: Record<AlertRow["type"], string> = {
  duplicate_therapy: "Duplicate medicine",
  allergy_conflict: "Allergy conflict",
  prescribing_cascade: "Prescribing cascade",
  lab_drift: "Lab trend",
  interaction: "Drug interaction",
};

export function SeverityBadge({ severity }: { severity: AlertRow["severity"] }) {
  // Status colour is never the only cue: icon + text label.
  if (severity === "critical")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-critical px-2 py-0.5 text-xs font-semibold text-white">
        <AlertOctagon className="size-3.5" /> Critical
      </span>
    );
  if (severity === "warning")
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-warning px-2 py-0.5 text-xs font-semibold text-white">
        <AlertTriangle className="size-3.5" /> Warning
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-semibold">
      <Info className="size-3.5" /> Info
    </span>
  );
}

export function AlertCard({
  alert: a,
  colors,
  audience,
  actions,
}: {
  alert: AlertRow;
  colors?: OrgColors;
  audience: "patient" | "doctor";
  actions?: React.ReactNode;
}) {
  const viewer = useDocumentViewer();
  const inactive = a.status !== "active";
  return (
    <article
      className={cn(
        "overflow-hidden rounded-xl border bg-card",
        !inactive && a.severity === "critical" && "border-critical/50",
        !inactive && a.severity === "warning" && "border-warning/50",
        inactive && "opacity-75",
      )}
    >
      <div
        className={cn(
          "flex flex-wrap items-center gap-2 px-4 py-2.5",
          !inactive && a.severity === "critical" && "bg-critical-soft",
          !inactive && a.severity === "warning" && "bg-warning-soft",
          inactive && "bg-muted/50",
        )}
      >
        <SeverityBadge severity={a.severity} />
        <span className="text-xs font-medium text-muted-foreground">{ALERT_TYPE_LABEL[a.type]}</span>
        {a.status !== "active" && (
          <Badge variant="secondary" className="ml-auto gap-1">
            <CheckCircle2 className="size-3" /> {a.status === "reviewed_intentional" ? "Reviewed — intentional" : a.status}
          </Badge>
        )}
      </div>
      <div className="space-y-3 p-4">
        <h3 className="leading-snug font-semibold">{a.title}</h3>
        <p className="text-sm leading-relaxed">{audience === "patient" ? a.patient_text : a.clinical_text}</p>
        {a.review_note && (
          <p className="rounded-lg bg-muted/60 px-3 py-2 text-sm">
            <span className="font-medium">Doctor&apos;s note:</span> {a.review_note}
          </p>
        )}
        <div>
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">Found in</p>
          <ul className="flex flex-wrap gap-1.5">
            {a.evidence.map((e) => (
              <li key={e.ref}>
                <button
                  disabled={!e.document_id}
                  onClick={() =>
                    e.document_id &&
                    viewer.open({ documentId: e.document_id, page: e.page ?? 1, snippet: e.snippet, title: `${e.doc_label} · page ${e.page}` })
                  }
                  className="inline-flex max-w-full items-center gap-1.5 rounded-lg border bg-background px-2 py-1 text-left text-xs hover:border-primary/50 hover:bg-accent/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-default"
                  title={e.snippet ?? undefined}
                >
                  <OrgDot color={orgColor(colors, e.org)} />
                  <span className="truncate">{e.label}</span>
                  <span className="shrink-0 text-muted-foreground">
                    · {fmtDate(e.date, "MMM yyyy")}
                    {e.doc_label ? ` · ${e.doc_label}` : ""}
                  </span>
                  {e.document_id && <FileText className="size-3 shrink-0 text-primary" />}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
            {a.details.explanation_source === "ai" && <Sparkles className="size-3" />}
            Detected by safety rules{a.details.explanation_source === "ai" ? " · explained by AI" : ""} · decision support only
          </span>
          {actions}
        </div>
      </div>
    </article>
  );
}
