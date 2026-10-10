import type { Metadata } from "next";

import { DoctorProfileView } from "@/components/doctor/profile-view";

export const metadata: Metadata = { title: "Professional profile" };

export default function Page() {
  return <DoctorProfileView />;
}
