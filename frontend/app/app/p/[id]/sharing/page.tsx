import type { Metadata } from "next";

import { SharingSection } from "@/components/patient/sections";

export const metadata: Metadata = { title: "Sharing" };

export default function Page() {
  return <SharingSection />;
}
