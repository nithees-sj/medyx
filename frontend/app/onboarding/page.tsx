import type { Metadata } from "next";
import { Suspense } from "react";

import { OnboardingFlow } from "@/components/auth/onboarding-flow";

export const metadata: Metadata = { title: "Set up your account" };

export default function OnboardingPage() {
  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-10">
      <Suspense fallback={null}>
        <OnboardingFlow />
      </Suspense>
    </main>
  );
}
