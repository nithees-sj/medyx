import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginPanel } from "@/components/auth/login-panel";
import { Logo } from "@/components/brand/logo";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main className="grid flex-1 lg:grid-cols-2">
      <section className="hidden flex-col justify-between bg-primary p-10 text-primary-foreground lg:flex">
        <Logo className="[&_rect]:fill-white/15" />
        <div className="max-w-md space-y-6">
          <h1 className="text-3xl leading-tight font-semibold">
            Every hospital&apos;s records, finally in one thread.
          </h1>
          <ul className="space-y-3 text-primary-foreground/85">
            <li>• Upload prescriptions, lab reports and discharge summaries from anywhere.</li>
            <li>• See duplicate medicines, allergy conflicts and silent lab trends across hospitals.</li>
            <li>• Share with a doctor by QR, for exactly as long as you choose.</li>
          </ul>
        </div>
        <p className="text-xs text-primary-foreground/60">Decision support only · synthetic demo data</p>
      </section>
      <section className="flex items-center justify-center px-4 py-10">
        <Suspense fallback={null}>
          <LoginPanel />
        </Suspense>
      </section>
    </main>
  );
}
