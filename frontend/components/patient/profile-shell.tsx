"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";

import { DocumentViewerProvider } from "@/components/record/viewer-context";
import { ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { profileLabel, useProfile } from "@/lib/hooks/profiles";
import { cn } from "@/lib/utils";

const NAV = [
  { slug: "timeline", label: "Timeline" },
  { slug: "alerts", label: "Alerts" },
  { slug: "trends", label: "Lab trends" },
  { slug: "medications", label: "Medicines" },
  { slug: "documents", label: "Documents" },
  { slug: "upload", label: "Upload" },
  { slug: "review", label: "Review" },
  { slug: "sharing", label: "Sharing" },
  { slug: "access-log", label: "Access log" },
  { slug: "emergency", label: "Emergency card" },
];

export function useProfileId(): string {
  return useParams<{ id: string }>().id;
}

export function ProfileShell({ children }: { children: React.ReactNode }) {
  const id = useProfileId();
  const pathname = usePathname();
  const { data: profile, isError, error, refetch } = useProfile(id);
  const base = `/app/p/${id}`;

  if (isError) return <ErrorState error={error} onRetry={() => refetch()} />;

  return (
    <DocumentViewerProvider>
      <div className="space-y-5">
        <div className="space-y-3">
          <Link href="/app" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-4" /> All profiles
          </Link>
          {profile ? (
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{profile.display_name}</h1>
                <p className="text-sm text-muted-foreground">
                  {profileLabel(profile)} · {profile.age} yrs · {profile.blood_group !== "unknown" ? profile.blood_group : "blood group not recorded"}
                </p>
              </div>
              <p className="font-mono text-xs tracking-wider text-muted-foreground">{profile.healththread_id}</p>
            </div>
          ) : (
            <Skeleton className="h-12 w-64" />
          )}
          <nav aria-label="Profile sections" className="-mx-4 overflow-x-auto px-4">
            <ul className="flex min-w-max gap-1 border-b">
              {NAV.map((n) => {
                const href = `${base}/${n.slug}`;
                const active = pathname === href;
                const badge =
                  n.slug === "review" ? profile?.pending_review : n.slug === "alerts" ? profile?.active_alerts : 0;
                return (
                  <li key={n.slug}>
                    <Link
                      href={href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                        active ? "border-primary font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {n.label}
                      {!!badge && (
                        <span
                          className={cn(
                            "rounded-full px-1.5 text-[10px] font-semibold",
                            n.slug === "alerts" && profile?.critical_alerts ? "bg-critical text-white" : "bg-warning text-white",
                          )}
                        >
                          {badge}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        </div>
        {children}
      </div>
    </DocumentViewerProvider>
  );
}
