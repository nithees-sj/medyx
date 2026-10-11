"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import {
  BadgeCheck,
  FilePen,
  Loader2,
  LogIn,
  type LucideIcon,
  Pause,
  Play,
  ServerCrash,
  Share2,
  ShieldAlert,
  Siren,
  Stethoscope,
} from "lucide-react";
import { useState } from "react";

import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/states";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { fmtInstant } from "@/lib/format";
import type { ActivityItem } from "@/lib/hooks/admin";
import { cn } from "@/lib/utils";

export const CATEGORY: Record<string, { label: string; icon: LucideIcon }> = {
  clinical_access: { label: "Clinical access", icon: Stethoscope },
  record_change: { label: "Record changes", icon: FilePen },
  sharing: { label: "Sharing", icon: Share2 },
  emergency: { label: "Emergency card", icon: Siren },
  auth: { label: "Sign-ins & accounts", icon: LogIn },
  security: { label: "Security", icon: ShieldAlert },
  verification: { label: "Doctor verification", icon: BadgeCheck },
  errors: { label: "Errors", icon: ServerCrash },
};

type Filters = { source?: string; category?: string; severity?: string; limit?: number; live?: boolean };

export function useActivity({ source = "all", category, severity, limit = 50, live = true }: Filters) {
  return useInfiniteQuery({
    queryKey: ["admin", "activity", source, category, severity, limit],
    queryFn: ({ pageParam }) => {
      const q = new URLSearchParams({ source, limit: String(limit) });
      if (category) q.set("category", category);
      if (severity) q.set("severity", severity);
      if (pageParam) q.set("before", pageParam);
      return api.get<{ items: ActivityItem[]; next_before: string | null }>(`/admin/activity?${q}`);
    },
    initialPageParam: "",
    getNextPageParam: (last) => last.next_before ?? undefined,
    refetchInterval: live ? 10_000 : false,
  });
}

export function ActivityList({ items, compact }: { items: ActivityItem[]; compact?: boolean }) {
  if (!items.length) return <p className="text-sm text-muted-foreground">No activity yet.</p>;
  return (
    <ol className="divide-y">
      {items.map((i) => {
        const cat = CATEGORY[i.category] ?? CATEGORY.auth;
        return (
          <li key={i.id} className="flex gap-3 py-2.5">
            <span
              className={cn(
                "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full",
                i.severity === "error" ? "bg-critical-soft" : i.severity === "warning" ? "bg-warning-soft" : "bg-muted",
              )}
              title={cat.label}
            >
              <cat.icon
                className={cn(
                  "size-3.5",
                  i.severity === "error" ? "text-critical" : i.severity === "warning" ? "text-warning" : "text-muted-foreground",
                )}
              />
            </span>
            <div className="min-w-0 flex-1 text-sm">
              <p className="break-words">
                {i.source === "record" ? (
                  <>
                    <span className="font-medium">{i.actor}</span>
                    {i.actor_role && <span className="ml-1 text-xs text-muted-foreground">({i.actor_role})</span>} {i.summary}
                  </>
                ) : (
                  // System messages already name who did what.
                  <>
                    {i.summary}
                    {i.actor_role && <span className="ml-1 text-xs text-muted-foreground">({i.actor_role})</span>}
                  </>
                )}
                {i.target && (
                  <>
                    {" "}
                    <span className="text-muted-foreground">on</span>{" "}
                    <span className="rounded bg-muted px-1 font-mono text-xs">{i.target}</span>
                  </>
                )}
              </p>
              <p className="text-xs text-muted-foreground">
                <time dateTime={i.at} title={fmtInstant(i.at)}>
                  {fmtInstant(i.at, compact ? "h:mm a" : "d MMM, h:mm:ss a")}
                </time>
                {!compact && (
                  <>
                    {" · "}
                    {cat.label}
                    {i.ip && ` · ${i.ip}`}
                  </>
                )}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

const SEVERITIES = [
  { value: "", label: "Any severity" },
  { value: "warning", label: "Warnings" },
  { value: "error", label: "Errors" },
];

export function ActivityView() {
  const [category, setCategory] = useState<string>("");
  const [severity, setSeverity] = useState<string>("");
  const [live, setLive] = useState(true);
  const feed = useActivity({ category: category || undefined, severity: severity || undefined, live });
  const items = feed.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Activity log"
        description="Everything happening on the platform: record access and changes (patients shown only by HealthThread ID), sign-ins, security events, doctor verification and errors."
        actions={
          <Button variant="outline" size="sm" onClick={() => setLive((v) => !v)} aria-pressed={live}>
            {live ? <Pause /> : <Play />} {live ? "Live" : "Paused"}
          </Button>
        }
      />
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by category">
        <Chip active={!category} onClick={() => setCategory("")}>
          All
        </Chip>
        {Object.entries(CATEGORY).map(([k, v]) => (
          <Chip key={k} active={category === k} onClick={() => setCategory(k)}>
            <v.icon className="size-3.5" /> {v.label}
          </Chip>
        ))}
        <span className="mx-1 w-px self-stretch bg-border" />
        {SEVERITIES.map((s) => (
          <Chip key={s.value} active={severity === s.value} onClick={() => setSeverity(s.value)}>
            {s.label}
          </Chip>
        ))}
      </div>
      {feed.isLoading ? (
        <LoadingState rows={8} />
      ) : feed.isError ? (
        <ErrorState error={feed.error} onRetry={() => feed.refetch()} />
      ) : !items.length ? (
        <EmptyState icon={CATEGORY[category]?.icon ?? LogIn} title="No matching activity" />
      ) : (
        <div className="rounded-xl border bg-card px-4">
          <ActivityList items={items} />
        </div>
      )}
      {feed.hasNextPage && (
        <div className="flex justify-center">
          <Button variant="outline" onClick={() => feed.fetchNextPage()} disabled={feed.isFetchingNextPage}>
            {feed.isFetchingNextPage && <Loader2 className="animate-spin" />} Load older activity
          </Button>
        </div>
      )}
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
        active ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}
