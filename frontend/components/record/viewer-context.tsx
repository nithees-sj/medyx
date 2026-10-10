"use client";

import dynamic from "next/dynamic";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";

const DocumentViewer = dynamic(() => import("@/components/record/document-viewer"), {
  ssr: false,
  loading: () => <Skeleton className="h-[70vh] w-full" />,
});

export interface OpenDocumentArgs {
  documentId: string;
  page?: number;
  snippet?: string | null;
  title?: string;
}

const ViewerContext = createContext<{ open: (args: OpenDocumentArgs) => void } | null>(null);

/** Lets any component (timeline drawer, citation chip, documents list) open a source page. */
export function DocumentViewerProvider({ children }: { children: React.ReactNode }) {
  const [current, setCurrent] = useState<OpenDocumentArgs | null>(null);
  const open = useCallback((args: OpenDocumentArgs) => setCurrent(args), []);
  const value = useMemo(() => ({ open }), [open]);
  return (
    <ViewerContext.Provider value={value}>
      {children}
      <Sheet open={!!current} onOpenChange={(o) => !o && setCurrent(null)}>
        <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-2xl">
          <SheetHeader className="border-b">
            <SheetTitle>{current?.title ?? "Source document"}</SheetTitle>
            <SheetDescription>
              {current?.snippet ? "The quoted text is highlighted on the page." : "Original document as uploaded."}
            </SheetDescription>
          </SheetHeader>
          {current && (
            <DocumentViewer
              key={`${current.documentId}:${current.page}:${current.snippet}`}
              documentId={current.documentId}
              initialPage={current.page ?? 1}
              snippet={current.snippet ?? null}
            />
          )}
        </SheetContent>
      </Sheet>
    </ViewerContext.Provider>
  );
}

export function useDocumentViewer() {
  const ctx = useContext(ViewerContext);
  if (!ctx) throw new Error("useDocumentViewer must be used inside DocumentViewerProvider");
  return ctx;
}
