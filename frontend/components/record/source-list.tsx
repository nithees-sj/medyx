"use client";

import { FileText } from "lucide-react";

import { OrgDot } from "@/components/record/org-chip";
import { useDocumentViewer } from "@/components/record/viewer-context";
import { fmtDate } from "@/lib/format";
import type { OrgColors, SourceRef } from "@/lib/record-types";
import { orgColor } from "@/lib/hooks/record";

/** "Where did this come from?" — each source opens the original page with the quote highlighted. */
export function SourceList({ sources, colors }: { sources: SourceRef[]; colors?: OrgColors }) {
  const viewer = useDocumentViewer();
  if (!sources.length) return <p className="text-sm text-muted-foreground">No source document.</p>;
  return (
    <ul className="space-y-2">
      {sources.map((s, i) => (
        <li key={`${s.document_id}-${s.page}-${i}`}>
          <button
            onClick={() =>
              viewer.open({ documentId: s.document_id, page: s.page, snippet: s.snippet, title: `${s.doc_label} · page ${s.page}` })
            }
            className="w-full rounded-lg border bg-card p-3 text-left text-sm transition-colors hover:border-primary/40 hover:bg-accent/30 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            <span className="flex items-center gap-2 font-medium">
              <FileText className="size-4 text-primary" />
              {s.doc_label} · page {s.page}
              <span className="ml-auto text-xs font-normal text-muted-foreground">{fmtDate(s.document_date)}</span>
            </span>
            <span className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
              <OrgDot color={orgColor(colors, s.org)} /> {s.org ?? "Unknown source"}
            </span>
            {s.snippet && <span className="mt-1.5 block text-xs italic text-foreground/80">“{s.snippet}”</span>}
          </button>
        </li>
      ))}
    </ul>
  );
}
