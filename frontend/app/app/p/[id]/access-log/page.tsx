import type { Metadata } from "next";

import { AccessLogSection } from "@/components/patient/sections";

export const metadata: Metadata = { title: "Access log" };

export default function Page() {
  return <AccessLogSection />;
}
