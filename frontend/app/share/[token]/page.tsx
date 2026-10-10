import type { Metadata } from "next";
import { Suspense } from "react";

import { ClaimView } from "@/components/doctor/claim-view";

export const metadata: Metadata = { title: "Shared record" };

export default function SharePage() {
  return (
    <Suspense fallback={null}>
      <ClaimView />
    </Suspense>
  );
}
