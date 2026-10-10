import type { Metadata } from "next";

import { EmergencySection } from "@/components/patient/sections";

export const metadata: Metadata = { title: "Emergency card" };

export default function Page() {
  return <EmergencySection />;
}
