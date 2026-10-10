import type { Metadata } from "next";

import { AlertsSection } from "@/components/patient/sections";

export const metadata: Metadata = { title: "Alerts" };

export default function Page() {
  return <AlertsSection />;
}
