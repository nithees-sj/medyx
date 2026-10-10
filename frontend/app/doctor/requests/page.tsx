import type { Metadata } from "next";

import { RequestsView } from "@/components/doctor/requests-view";

export const metadata: Metadata = { title: "Request access" };

export default function Page() {
  return <RequestsView />;
}
