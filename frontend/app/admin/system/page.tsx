import type { Metadata } from "next";

import { SystemView } from "@/components/admin/system";

export const metadata: Metadata = { title: "Admin · System" };

export default function Page() {
  return <SystemView />;
}
