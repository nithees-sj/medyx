"use client";

import { FileText, HelpCircle } from "lucide-react";
import { Fragment } from "react";

import { useDocumentViewer } from "@/components/record/viewer-context";
import type { Citation } from "@/lib/hooks/doctor";
import { cn } from "@/lib/utils";

const KEY_RE = /\[((?:Condition|Observation|MedicationRequest|AllergyIntolerance|DocumentReference)\/[A-Za-z0-9.-]+)\]/g;

/** A citation chip: opens the source page with the snippet highlighted. */
export function CitationChip({ c, pending }: { c?: Citation; pending?: string }) {
  const viewer = useDocumentViewer();
  if (!c || c.unknown || !c.document_id) {
    return (
      <span
        className="mx-0.5 inline-flex items-center gap-1 rounded-md border border-dashed px-1.5 py-0 align-baseline text-[11px] text-muted-foreground"
        title={c?.unknown ? "This reference isn't in the record" : "Source"}
      >
        {c?.unknown ? <HelpCircle className="size-3" /> : <FileText className="size-3" />}
        {c?.label ?? pending ?? c?.key}
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={() => viewer.open({ documentId: c.document_id!, page: c.page ?? 1, snippet: c.snippet, title: `${c.doc_label} · page ${c.page}` })}
      className="mx-0.5 inline-flex max-w-[16rem] items-center gap-1 rounded-md border border-primary/30 bg-accent/60 px-1.5 py-0 align-baseline text-[11px] font-medium text-accent-foreground hover:border-primary focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
      title={c.snippet ? `“${c.snippet}” — ${c.org ?? ""}` : c.org ?? undefined}
    >
      <FileText className="size-3 shrink-0" />
      <span className="truncate">{c.label}</span>
      <span className="shrink-0 text-muted-foreground">
        {c.doc_label} p{c.page}
      </span>
    </button>
  );
}

function renderInline(text: string, map: Map<string, Citation>, pending: boolean) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(KEY_RE)) {
    if (m.index! > last) parts.push(text.slice(last, m.index));
    const c = map.get(m[1]);
    parts.push(<CitationChip key={`${m.index}-${m[1]}`} c={c ?? (pending ? undefined : { key: m[1], unknown: true })} pending={pending ? m[1].split("/")[0] : undefined} />);
    last = m.index! + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

/** Plain text with "- " bullets and [Type/id] keys rendered as clickable source chips. */
export function CitedText({ text, citations, pending = false, className }: { text: string; citations: Citation[]; pending?: boolean; className?: string }) {
  const map = new Map(citations.map((c) => [c.key, c]));
  const lines = text.split("\n");
  return (
    <div className={cn("space-y-1.5 text-sm leading-relaxed", className)}>
      {lines.map((line, i) => {
        const bullet = /^\s*[-*•]\s+/.test(line);
        const content = line.replace(/^\s*[-*•]\s+/, "").replace(/\*\*(.+?)\*\*/g, "$1");
        if (!content.trim()) return <Fragment key={i} />;
        return bullet ? (
          <p key={i} className="flex gap-2 pl-1">
            <span className="mt-2 size-1 shrink-0 rounded-full bg-muted-foreground" />
            <span>{renderInline(content, map, pending)}</span>
          </p>
        ) : (
          <p key={i}>{renderInline(content, map, pending)}</p>
        );
      })}
    </div>
  );
}
