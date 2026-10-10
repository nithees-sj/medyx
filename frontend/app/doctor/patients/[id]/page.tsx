import type { Metadata } from "next";

import { Workspace } from "@/components/doctor/workspace";

export const metadata: Metadata = { title: "Patient workspace" };

export default function Page() {
  return <Workspace />;
}
