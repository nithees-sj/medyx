import type { Metadata } from "next";

import { MedicationsSection } from "@/components/patient/sections";

export const metadata: Metadata = { title: "Medicines" };

export default function Page() {
  return <MedicationsSection />;
}
