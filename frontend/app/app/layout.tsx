import { PatientShell } from "@/components/shell/role-shells";

export default function PatientLayout({ children }: LayoutProps<"/app">) {
  return <PatientShell>{children}</PatientShell>;
}
