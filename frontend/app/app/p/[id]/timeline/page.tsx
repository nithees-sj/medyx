import type { Metadata } from "next";

import { TimelineSection } from "@/components/patient/sections";

export const metadata: Metadata = { title: "Timeline" };

export default function Page() {
  return <TimelineSection />;
}
