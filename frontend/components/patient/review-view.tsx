"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ClipboardCheck, Loader2, Pencil, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useDocumentViewer } from "@/components/record/viewer-context";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { recordKeys, useReviewQueue } from "@/lib/hooks/record";
import type { ReviewItem } from "@/lib/record-types";

const TYPE_LABEL: Record<string, string> = {
  Condition: "Condition",
  MedicationRequest: "Medicine",
  AllergyIntolerance: "Allergy",
  Observation: "Lab result",
  Vital: "Vital sign",
};

const FIELD_LABEL: Record<string, string> = {
  text: "Condition",
  icd10_guess: "ICD-10 code",
  onset_date: "Since (date)",
  clinical_status: "Status",
  brand: "Brand",
  generic_molecule: "Generic medicine",
  strength: "Strength",
  form: "Form",
  frequency_text: "How often (e.g. 1-0-1)",
  duration_days: "For how many days",
  start_date: "Start date",
  instructions: "Instructions",
  substance: "Allergic to",
  reaction: "Reaction",
  criticality: "Severity",
  recorded_date: "Recorded on",
  test_name_as_written: "Test name",
  value: "Value",
  unit_as_written: "Unit",
  reference_range_text: "Reference range",
  specimen_date: "Sample date",
  name: "Vital sign",
  unit: "Unit",
  date: "Date",
};

function summary(item: ReviewItem): string {
  const r = item.raw as Record<string, string | number | null>;
  switch (item.resource_type) {
    case "AllergyIntolerance":
      return `${r.substance}${r.reaction ? ` — ${r.reaction}` : ""}`;
    case "MedicationRequest":
      return String(r.written_text ?? r.generic_molecule);
    case "Condition":
      return String(r.text);
    case "Observation":
      return `${r.test_name_as_written}: ${r.value} ${r.unit_as_written ?? ""}`;
    default:
      return `${r.name}: ${r.value} ${r.unit ?? ""}`;
  }
}

export function ReviewView({ profileId }: { profileId: string }) {
  const { data, isLoading, isError, error, refetch } = useReviewQueue(profileId);
  if (isLoading) return <LoadingState rows={2} />;
  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data?.length)
    return (
      <EmptyState
        icon={ClipboardCheck}
        title="Nothing to review"
        description="When something on a document is hard to read, we'll ask you to check it here before it goes into the record."
      />
    );
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        We weren&apos;t fully sure about {data.length === 1 ? "this item" : `these ${data.length} items`}. Check them against the
        original. Nothing here is added to the record until you confirm.
      </p>
      {data.map((item) => (
        <ReviewCard key={item.id} profileId={profileId} item={item} />
      ))}
    </div>
  );
}

function ReviewCard({ profileId, item }: { profileId: string; item: ReviewItem }) {
  const qc = useQueryClient();
  const viewer = useDocumentViewer();
  const [editing, setEditing] = useState(false);
  const [fields, setFields] = useState<Record<string, string>>(() =>
    Object.fromEntries(item.editable.map((k) => [k, item.raw[k] == null ? "" : String(item.raw[k])])),
  );
  const act = useMutation({
    mutationFn: (action: "confirm" | "correct" | "reject") => {
      const changed =
        action === "correct"
          ? Object.fromEntries(
              Object.entries(fields)
                .filter(([k, v]) => v !== (item.raw[k] == null ? "" : String(item.raw[k])))
                .map(([k, v]) => [k, k === "value" ? Number(v) : k === "duration_days" ? (v ? Number(v) : null) : v || null]),
            )
          : undefined;
      return api.post<{ status: string }>(`/review/${item.id}`, { action, fields: changed });
    },
    onSuccess: (r) => {
      toast.success(r.status === "rejected" ? "Removed" : "Added to the record");
      qc.invalidateQueries({ queryKey: recordKeys.all(profileId) });
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["profile", profileId] });
      qc.invalidateQueries({ queryKey: ["alerts", profileId] });
    },
    onError: (e) => toast.error(e.message),
  });

  const isPdf = item.document_mime === "application/pdf";
  const crop = `/api/documents/${item.document_id}/pages/${item.page}.png?${new URLSearchParams({
    ...(item.snippet ? { highlight: item.snippet } : {}),
    crop: "1",
  })}`;

  return (
    <article className="overflow-hidden rounded-xl border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5 text-sm">
        <span className="font-medium">
          <Badge variant="secondary" className="mr-2">
            {TYPE_LABEL[item.resource_type]}
          </Badge>
          {summary(item)}
        </span>
        <span className="text-xs text-muted-foreground">
          {item.document_label} · page {item.page} · {item.source_org_name} · {fmtDate(item.document_date)}
        </span>
      </div>
      <div className="grid gap-4 p-4 md:grid-cols-2">
        <div className="space-y-2">
          <button
            onClick={() => viewer.open({ documentId: item.document_id, page: item.page, snippet: item.snippet, title: `${item.document_label} · page ${item.page}` })}
            className="block w-full overflow-hidden rounded-lg border bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
            aria-label="Open the full page"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={isPdf ? crop : `/api/documents/${item.document_id}/file`} alt="Part of the original page" className="max-h-72 w-full object-contain" />
          </button>
          {item.snippet && <p className="text-sm italic">“{item.snippet}”</p>}
          {item.uncertain_reason && (
            <p className="flex gap-1.5 text-sm text-warning">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {item.uncertain_reason}
            </p>
          )}
          <p className="text-xs text-muted-foreground">Confidence {(item.confidence * 100).toFixed(0)}%</p>
        </div>
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            {item.editable.map((k) => (
              <Field key={k} label={FIELD_LABEL[k] ?? k} htmlFor={`${item.id}-${k}`}>
                <Input
                  id={`${item.id}-${k}`}
                  value={fields[k]}
                  disabled={!editing}
                  type={k === "value" || k === "duration_days" ? "number" : k.endsWith("date") ? "date" : "text"}
                  step="any"
                  onChange={(e) => setFields((f) => ({ ...f, [k]: e.target.value }))}
                />
              </Field>
            ))}
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            {editing ? (
              <Button onClick={() => act.mutate("correct")} disabled={act.isPending}>
                {act.isPending ? <Loader2 className="animate-spin" /> : <Check />} Save correction
              </Button>
            ) : (
              <Button onClick={() => act.mutate("confirm")} disabled={act.isPending}>
                {act.isPending ? <Loader2 className="animate-spin" /> : <Check />} Looks right
              </Button>
            )}
            <Button variant="outline" onClick={() => setEditing((e) => !e)} disabled={act.isPending}>
              <Pencil /> {editing ? "Cancel edit" : "Correct"}
            </Button>
            <Button variant="ghost" onClick={() => act.mutate("reject")} disabled={act.isPending}>
              <X /> Not on the document
            </Button>
          </div>
        </div>
      </div>
    </article>
  );
}
