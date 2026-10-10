import type { Metadata } from "next";
import { Suspense } from "react";

import { PublicEmergencyCard } from "@/components/emergency/public-card";

export const metadata: Metadata = { title: "Emergency card", robots: { index: false, follow: false } };

export default function EmergencyPage() {
  return (
    <Suspense fallback={null}>
      <PublicEmergencyCard />
    </Suspense>
  );
}
