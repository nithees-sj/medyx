import { Suspense } from "react";

import { PatientShell } from "@/components/shell/role-shells";
import { ShellSkeleton } from "@/components/shell/shell-skeleton";

// Everything below renders on the client after the role check, so URL hooks stream in behind Suspense.
export default function Layout({ children }: LayoutProps<"/app">) {
  return (
    <Suspense fallback={<ShellSkeleton />}>
      <PatientShell>{children}</PatientShell>
    </Suspense>
  );
}
