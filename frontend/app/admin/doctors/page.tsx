import type { Metadata } from "next";

import { DoctorVerification } from "@/components/admin/doctors";

export const metadata: Metadata = { title: "Admin · Doctors" };

export default function Page() {
  return <DoctorVerification />;
}
