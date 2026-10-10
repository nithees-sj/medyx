import type { Metadata } from "next";

import { ReviewSection } from "@/components/patient/sections";

export const metadata: Metadata = { title: "Review" };

export default function Page() {
  return <ReviewSection />;
}
