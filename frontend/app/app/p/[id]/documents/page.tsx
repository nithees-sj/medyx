import type { Metadata } from "next";

import { DocumentsSection } from "@/components/patient/sections";

export const metadata: Metadata = { title: "Documents" };

export default function Page() {
  return <DocumentsSection />;
}
