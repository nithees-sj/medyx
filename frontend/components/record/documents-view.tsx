"use client";

import { AlertCircle, CheckCircle2, ClipboardCheck, FileImage, FileText, Loader2, RotateCw } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { ExplainDialog } from "@/components/patient/explain-dialog";
import { OrgChip } from "@/components/record/org-chip";
import { useDocumentViewer } from "@/components/record/viewer-context";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { api } from "@/lib/api";
import { countsSummary, docTypeLabel, fmtDate } from "@/lib/format";
import { orgColor, recordKeys, useDocuments, useOrgColors } from "@/lib/hooks/record";
import type { DocumentRow } from "@/lib/record-types";

export function DocumentStatus({ doc }: { doc: DocumentRow }) {
  if (doc.status === "done")
    return (
      <span className="inline-flex items-center gap-1 text-xs text-success">
        <CheckCircle2 className="size-3.5" /> Added to record
      </span>
    );
  if (doc.status === "needs_review")
    return (
      <span className="inline-flex items-center gap-1 text-xs text-warning">
        <ClipboardCheck className="size-3.5" /> Needs your review
      </span>
    );
  if (doc.status === "failed")
    return (
      <span className="inline-flex items-center gap-1 text-xs text-critical">
        <AlertCircle className="size-3.5" /> Failed
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <Loader2 className="size-3.5 animate-spin" /> {doc.stage}
    </span>
  );
}

export function DocumentsView({
  profileId,
  reviewHref,
  emptyAction,
  canRetry = false,
  canExplain = false,
}: {
  profileId: string;
  reviewHref?: string;
  emptyAction?: React.ReactNode;
  canRetry?: boolean;
  canExplain?: boolean;
}) {
  const { data, isLoading, isError, error, refetch } = useDocuments(profileId);
  const colors = useOrgColors(profileId).data;
  const viewer = useDocumentViewer();
  const qc = useQueryClient();
  const [org, setOrg] = useState("");
  const [type, setType] = useState("");
  const retry = useMutation({
    mutationFn: (id: string) => api.post(`/documents/${id}/retry`),
    onSuccess: () => qc.invalidateQueries({ queryKey: recordKeys.docs(profileId) }),
    onError: (e) => toast.error(e.message),
  });

  const orgs = useMemo(() => [...new Set((data ?? []).map((d) => d.source_org_name).filter(Boolean))] as string[], [data]);
  const types = useMemo(() => [...new Set((data ?? []).map((d) => d.document_type).filter(Boolean))] as string[], [data]);

  if (isLoading) return <LoadingState rows={5} />;
  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data?.length)
    return (
      <EmptyState
        icon={FileText}
        title="No documents yet"
        description="PDFs, phone photos and scans from any hospital, clinic or lab."
        action={emptyAction}
      />
    );
  const shown = data.filter((d) => (!org || d.source_org_name === org) && (!type || d.document_type === type));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <div className="w-full sm:w-64">
          <NativeSelect aria-label="Filter by hospital" value={org} onChange={(e) => setOrg(e.target.value)}>
            <option value="">All hospitals & labs</option>
            {orgs.map((o) => (
              <option key={o}>{o}</option>
            ))}
          </NativeSelect>
        </div>
        <div className="w-full sm:w-52">
          <NativeSelect aria-label="Filter by type" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All types</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {docTypeLabel(t)}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>
      <ul className="space-y-2">
        {shown.map((d) => {
          const Icon = d.mime === "application/pdf" ? FileText : FileImage;
          return (
            <li key={d.id} className="flex flex-wrap items-center gap-3 rounded-xl border bg-card p-3 sm:p-4">
              <button
                onClick={() => viewer.open({ documentId: d.id, title: `${d.label} · ${d.original_filename}` })}
                disabled={d.status === "queued" || d.status === "processing"}
                className="flex min-w-0 flex-1 items-start gap-3 text-left focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-default"
              >
                <Icon className="mt-0.5 size-5 shrink-0 text-primary" />
                <span className="min-w-0 space-y-1">
                  <span className="block truncate font-medium">
                    <span className="text-muted-foreground">{d.label}</span> · {docTypeLabel(d.document_type)}
                    {d.document_date ? ` · ${fmtDate(d.document_date)}` : ""}
                  </span>
                  <span className="flex flex-wrap items-center gap-2">
                    <OrgChip name={d.source_org_name} color={orgColor(colors, d.source_org_name)} />
                    <span className="truncate text-xs text-muted-foreground">{d.original_filename}</span>
                  </span>
                  {d.status === "done" || d.status === "needs_review" ? (
                    <span className="block text-xs text-muted-foreground">{countsSummary(d.result_counts)}</span>
                  ) : d.error ? (
                    <span className="block text-xs text-critical">{d.error}</span>
                  ) : null}
                </span>
              </button>
              <div className="flex items-center gap-2">
                <DocumentStatus doc={d} />
                {d.status === "needs_review" && reviewHref && (
                  <Link href={reviewHref} className="text-xs font-medium text-primary hover:underline">
                    Review
                  </Link>
                )}
                {d.status === "failed" && canRetry && (
                  <Button size="xs" variant="outline" onClick={() => retry.mutate(d.id)} disabled={retry.isPending}>
                    <RotateCw /> Retry
                  </Button>
                )}
                {canExplain && d.status === "done" && <ExplainDialog documentId={d.id} label={d.label} />}
                {d.uploader_role === "doctor" && <Badge variant="secondary">Added by doctor</Badge>}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
