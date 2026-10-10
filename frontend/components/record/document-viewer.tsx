"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Download, Quote } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";

import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { docTypeLabel, fmtDate } from "@/lib/format";
import type { DocumentRow } from "@/lib/record-types";

// Must be set in the same module that renders <Document> (react-pdf docs).
pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9.%/]+/g, " ").trim();

export default function DocumentViewer({
  documentId,
  initialPage,
  snippet,
}: {
  documentId: string;
  initialPage: number;
  snippet: string | null;
}) {
  const meta = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api.get<DocumentRow>(`/documents/${documentId}`),
  });
  const [page, setPage] = useState(initialPage);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [width, setWidth] = useState(600);
  const [matched, setMatched] = useState(false);
  const fileUrl = `/api/documents/${documentId}/file`;

  const measure = useCallback((el: HTMLDivElement | null) => {
    // clientWidth includes the p-4 padding (2 × 16px).
    if (el) setWidth(Math.min(el.clientWidth - 34, 900));
  }, []);

  const needle = useMemo(() => (snippet ? norm(snippet) : ""), [snippet]);
  // Highlight text-layer items whose text appears in the quoted snippet (on the cited page only).
  const textRenderer = useCallback(
    ({ str }: { str: string }) => {
      const n = norm(str);
      const meaningful = n.length >= 3 || (/\d/.test(n) && n.length >= 2);
      if (page === initialPage && needle && meaningful && needle.includes(n)) {
        if (!matched) queueMicrotask(() => setMatched(true));
        return `<mark class="ht-mark">${str}</mark>`;
      }
      return str;
    },
    [needle, page, initialPage, matched],
  );

  if (meta.isError) return <ErrorState error={meta.error} onRetry={() => meta.refetch()} className="m-4" />;
  const doc = meta.data;
  const isPdf = doc?.mime === "application/pdf";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-2 text-sm">
        {doc ? (
          <span className="min-w-0 flex-1 truncate">
            <span className="font-medium">{doc.label}</span> · {docTypeLabel(doc.document_type)} ·{" "}
            {doc.source_org_name ?? "Unknown source"} · {fmtDate(doc.document_date)}
          </span>
        ) : (
          <Skeleton className="h-5 w-64" />
        )}
        <a href={fileUrl} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
          <Download className="size-4" /> Original
        </a>
      </div>

      {snippet && (
        <div className="mx-4 mt-3 flex gap-2 rounded-lg border border-warning/40 bg-warning-soft px-3 py-2 text-sm">
          <Quote className="mt-0.5 size-4 shrink-0 text-warning" />
          <div>
            <p className="text-xs font-medium text-muted-foreground">
              Quoted from page {initialPage}
              {isPdf && page === initialPage && !matched ? " (exact position not found — see quote)" : ""}
            </p>
            <p className="font-medium">“{snippet}”</p>
          </div>
        </div>
      )}

      <div ref={measure} className="min-h-0 flex-1 overflow-auto bg-muted/40 p-4">
        {!doc ? (
          <Skeleton className="h-[60vh] w-full" />
        ) : isPdf ? (
          <Document
            file={fileUrl}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            loading={<Skeleton className="h-[60vh] w-full" />}
            error={<ErrorState error={new Error("This PDF couldn't be displayed")} />}
          >
            <Page
              pageNumber={page}
              width={width}
              customTextRenderer={textRenderer}
              renderAnnotationLayer={false}
              className="mx-auto overflow-hidden rounded-md shadow-sm"
              loading={<Skeleton className="h-[60vh] w-full" />}
            />
          </Document>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={fileUrl} alt={`${doc.label} — ${doc.original_filename}`} className="mx-auto max-w-full rounded-md shadow-sm" />
        )}
      </div>

      {isPdf && numPages && numPages > 1 && (
        <div className="flex items-center justify-center gap-3 border-t px-4 py-2 text-sm">
          <Button variant="outline" size="icon-sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} aria-label="Previous page">
            <ChevronLeft />
          </Button>
          <span>
            Page {page} of {numPages}
          </span>
          <Button variant="outline" size="icon-sm" onClick={() => setPage((p) => Math.min(numPages, p + 1))} disabled={page >= numPages} aria-label="Next page">
            <ChevronRight />
          </Button>
        </div>
      )}
    </div>
  );
}
