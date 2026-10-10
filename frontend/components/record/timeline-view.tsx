"use client";

import "vis-timeline/styles/vis-timeline-graph2d.min.css";

import { CalendarRange, Maximize2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { OrgChip, OrgDot, OrgLegend } from "@/components/record/org-chip";
import { SourceList } from "@/components/record/source-list";
import { useDocumentViewer } from "@/components/record/viewer-context";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { fmtDate } from "@/lib/format";
import { orgColor, useTimeline } from "@/lib/hooks/record";
import type { TimelineData, TimelineItem } from "@/lib/record-types";

const GROUP_ORDER: Record<string, number> = { conditions: 0, medications: 1, labs: 2, documents: 3 };

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);
}

export function TimelineView({ profileId, emptyAction }: { profileId: string; emptyAction?: React.ReactNode }) {
  const { data, isLoading, isError, error, refetch } = useTimeline(profileId);
  const [selected, setSelected] = useState<TimelineItem | null>(null);
  const viewer = useDocumentViewer();

  if (isLoading) return <LoadingState rows={4} />;
  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data?.items.length)
    return (
      <EmptyState
        icon={CalendarRange}
        title="Nothing on the timeline yet"
        description="Upload prescriptions and reports from any hospital. They'll appear here in one thread."
        action={emptyAction}
      />
    );

  const onSelect = (item: TimelineItem) => {
    if (item.group === "documents" && item.document_id) {
      viewer.open({ documentId: item.document_id, title: item.title });
    } else {
      setSelected(item);
    }
  };

  return (
    <div className="space-y-4">
      <OrgLegend colors={data.org_colors} />
      <VisTimeline data={data} onSelect={onSelect} />
      <ChronoList data={data} onSelect={onSelect} />
      <Sheet open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <SheetContent side="right" className="w-full sm:max-w-md">
          {selected && (
            <>
              <SheetHeader>
                <SheetTitle>{selected.title}</SheetTitle>
                <SheetDescription>
                  {selected.kind === "range"
                    ? `${fmtDate(selected.start)} → ${selected.ongoing ? "ongoing" : fmtDate(selected.end)}`
                    : fmtDate(selected.start)}
                  {selected.subtitle ? ` · ${selected.subtitle}` : ""}
                </SheetDescription>
              </SheetHeader>
              <div className="space-y-4 px-4 pb-6">
                <div className="flex flex-wrap gap-2">
                  <OrgChip name={selected.org} color={orgColor(data.org_colors, selected.org)} />
                  {selected.status && <Badge variant="secondary">{selected.status}</Badge>}
                </div>
                <div>
                  <h3 className="mb-2 text-sm font-medium">Source</h3>
                  <SourceList sources={selected.sources} colors={data.org_colors} />
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function VisTimeline({ data, onSelect }: { data: TimelineData; onSelect: (item: TimelineItem) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const timelineRef = useRef<{ fit: () => void; destroy: () => void } | null>(null);
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  const byId = useMemo(() => new Map(data.items.map((i) => [i.id, i])), [data.items]);

  useEffect(() => {
    let disposed = false;
    import("vis-timeline/standalone").then((mod) => {
      if (disposed || !ref.current) return;
      // The standalone bundle also exports vis-data's DataSet (not in its type declarations).
      const { Timeline } = mod;
      const { DataSet } = mod as unknown as { DataSet: typeof import("vis-data").DataSet };
      const items = new DataSet(
        data.items.map((i) => {
          const color = orgColor(data.org_colors, i.org);
          const muted = i.status === "completed" || i.status === "stopped";
          // Short courses (a 5-day antibiotic) would be an unlabeled sliver as a range; show them as labeled points.
          const days = i.end ? (Date.parse(i.end) - Date.parse(i.start)) / 86_400_000 : 0;
          const asRange = i.kind === "range" && days >= 45;
          return {
            id: i.id,
            group: i.group,
            start: i.start,
            end: asRange ? i.end : undefined,
            type: asRange ? "range" : "point",
            content: escapeHtml(i.title),
            title: escapeHtml(`${i.title}${i.org ? ` — ${i.org}` : ""}`),
            className: `ht-item ${asRange ? "ht-range" : "ht-point"}${i.status === "H" || i.status === "L" ? " ht-abnormal" : ""}`,
            style: `--ht-org:${color};${muted ? "opacity:.6;" : ""}`,
          };
        }),
      );
      const groups = new DataSet(data.groups.map((g) => ({ id: g.id, content: g.label, order: GROUP_ORDER[g.id] })));
      const dates = data.items.flatMap((i) => [i.start, i.end].filter(Boolean) as string[]).map((d) => Date.parse(d));
      const min = Math.min(...dates);
      const max = Math.max(Date.now(), ...dates);
      const tl = new Timeline(ref.current, items, groups, {
        stack: true,
        orientation: "top",
        groupOrder: "order",
        margin: { item: { horizontal: 4, vertical: 6 }, axis: 6 },
        start: new Date(min - 1000 * 60 * 60 * 24 * 45),
        end: new Date(max + 1000 * 60 * 60 * 24 * 120),
        zoomMin: 1000 * 60 * 60 * 24 * 10,
        zoomMax: 1000 * 60 * 60 * 24 * 365 * 15,
        minHeight: 320,
        maxHeight: 560,
        selectable: true,
        showCurrentTime: true,
        zoomKey: "ctrlKey",
        horizontalScroll: true,
        verticalScroll: true,
      });
      tl.on("select", ({ items: sel }: { items: string[] }) => {
        const item = sel[0] ? byId.get(sel[0]) : undefined;
        if (item) onSelectRef.current(item);
        tl.setSelection([]);
      });
      timelineRef.current = tl;
    });
    return () => {
      disposed = true;
      timelineRef.current?.destroy();
      timelineRef.current = null;
    };
  }, [data, byId]);

  return (
    <div className="relative">
      <div ref={ref} className="ht-timeline overflow-hidden rounded-xl border bg-card" aria-label="Medical timeline" />
      <Button
        variant="outline"
        size="icon-sm"
        className="absolute top-2 right-2 bg-card"
        onClick={() => timelineRef.current?.fit()}
        aria-label="Fit whole history"
      >
        <Maximize2 />
      </Button>
      <p className="mt-1 text-xs text-muted-foreground">Drag to move · pinch or Ctrl + scroll to zoom · tap an item for its source.</p>
    </div>
  );
}

function ChronoList({ data, onSelect }: { data: TimelineData; onSelect: (item: TimelineItem) => void }) {
  const sorted = [...data.items].filter((i) => i.group !== "labs").sort((a, b) => b.start.localeCompare(a.start));
  const byYear = sorted.reduce<Record<string, TimelineItem[]>>((acc, i) => {
    (acc[i.start.slice(0, 4)] ??= []).push(i);
    return acc;
  }, {});
  return (
    <details className="group rounded-xl border bg-card">
      <summary className="cursor-pointer px-4 py-3 text-sm font-medium select-none">
        List view <span className="text-muted-foreground">(conditions, medicines and documents)</span>
      </summary>
      <div className="space-y-4 border-t px-4 py-3">
        {Object.entries(byYear).map(([year, items]) => (
          <section key={year}>
            <h3 className="mb-1 text-xs font-semibold tracking-wide text-muted-foreground">{year}</h3>
            <ul className="divide-y">
              {items.map((i) => (
                <li key={i.id}>
                  <button
                    onClick={() => onSelect(i)}
                    className="flex w-full items-start gap-2 py-2 text-left text-sm hover:text-primary focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                  >
                    <OrgDot color={orgColor(data.org_colors, i.org)} className="mt-1.5" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">{i.title}</span>
                      <span className="text-xs text-muted-foreground">
                        {fmtDate(i.start)} · {i.group === "medications" ? "Medicine" : i.group === "conditions" ? "Condition" : "Document"}
                        {i.org ? ` · ${i.org}` : ""}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </details>
  );
}
