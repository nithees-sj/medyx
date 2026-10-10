import type { Metadata } from "next";

import { TrendsSection } from "@/components/patient/sections";

export const metadata: Metadata = { title: "Lab trends" };

export default function Page() {
  return <TrendsSection />;
}
