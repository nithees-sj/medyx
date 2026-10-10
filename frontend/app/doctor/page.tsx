import type { Metadata } from "next";

import { DoctorDashboard } from "@/components/doctor/doctor-dashboard";

export const metadata: Metadata = { title: "Doctor dashboard" };

export default function DoctorPage() {
  return <DoctorDashboard />;
}
