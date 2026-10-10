import { ProfileShell } from "@/components/patient/profile-shell";

export default function ProfileLayout({ children }: LayoutProps<"/app/p/[id]">) {
  return <ProfileShell>{children}</ProfileShell>;
}
