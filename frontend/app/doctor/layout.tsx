import { DoctorShell } from "@/components/shell/role-shells";

export default function DoctorLayout({ children }: LayoutProps<"/doctor">) {
  return <DoctorShell>{children}</DoctorShell>;
}
