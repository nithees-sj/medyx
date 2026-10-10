"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { ErrorState } from "@/components/states";
import { Skeleton } from "@/components/ui/skeleton";
import { homeFor, useMe } from "@/lib/hooks/auth";
import type { Me, Role } from "@/lib/types";

/**
 * Client-side role check for a section of the app. The API enforces every rule
 * independently; this only routes people to the right screen.
 */
export function RoleGuard({
  role,
  children,
}: {
  role: Role | "onboarding";
  children: (me: Me) => React.ReactNode;
}) {
  const { data: me, isLoading, isError, error, refetch } = useMe();
  const router = useRouter();
  const pathname = usePathname();

  const allowed =
    me && (role === "onboarding" ? !me.role : me.role === role);

  useEffect(() => {
    if (isLoading || isError) return;
    if (me === null) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    } else if (me && !allowed) {
      router.replace(homeFor(me));
    }
  }, [me, isLoading, isError, allowed, router, pathname]);

  if (isError) {
    return (
      <div className="mx-auto w-full max-w-md p-6">
        <ErrorState error={error} onRetry={() => refetch()} />
      </div>
    );
  }
  if (!me || !allowed) {
    return (
      <div className="mx-auto w-full max-w-5xl space-y-4 p-6" aria-busy="true">
        <Skeleton className="h-10 w-48" />
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-32 w-full rounded-xl" />
      </div>
    );
  }
  return <>{children(me)}</>;
}
