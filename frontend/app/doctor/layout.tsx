import { Suspense } from "react";

import { DoctorShell } from "@/components/shell/role-shells";
import { ShellSkeleton } from "@/components/shell/shell-skeleton";

// Everything below renders on the client after the role check, so URL hooks stream in behind Suspense.
export default function Layout({ children }: LayoutProps<"/doctor">) {
  return (
    <Suspense fallback={<ShellSkeleton />}>
      <DoctorShell>{children}</DoctorShell>
    </Suspense>
  );
}
