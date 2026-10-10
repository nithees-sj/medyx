import type { Metadata } from "next";

import { UploadSection } from "@/components/patient/sections";

export const metadata: Metadata = { title: "Upload" };

export default function Page() {
  return <UploadSection />;
}
