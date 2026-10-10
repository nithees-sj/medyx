import type { Metadata } from "next";

import { PatientHome } from "@/components/patient/patient-home";

export const metadata: Metadata = { title: "Home" };

export default function PatientHomePage() {
  return <PatientHome />;
}
