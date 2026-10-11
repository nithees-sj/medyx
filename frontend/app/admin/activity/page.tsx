import type { Metadata } from "next";

import { ActivityView } from "@/components/admin/activity";

export const metadata: Metadata = { title: "Admin · Activity" };

export default function Page() {
  return <ActivityView />;
}
