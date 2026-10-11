import type { Metadata } from "next";

import { UsersView } from "@/components/admin/users";

export const metadata: Metadata = { title: "Admin · Users" };

export default function Page() {
  return <UsersView />;
}
