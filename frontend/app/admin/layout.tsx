import { Suspense } from "react";

import { AdminShell } from "@/components/shell/role-shells";
import { ShellSkeleton } from "@/components/shell/shell-skeleton";

// Everything below renders on the client after the role check, so URL hooks stream in behind Suspense.
export default function Layout({ children }: LayoutProps<"/admin">) {
  return (
    <Suspense fallback={<ShellSkeleton />}>
      <AdminShell>{children}</AdminShell>
    </Suspense>
  );
}
