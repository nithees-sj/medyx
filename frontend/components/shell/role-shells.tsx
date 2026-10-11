"use client";

import { ShieldCheck, Stethoscope } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { RoleGuard } from "@/components/auth/role-guard";
import { AppHeader } from "@/components/shell/app-header";
import { Badge } from "@/components/ui/badge";

export function PatientShell({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard role="patient">
      {(me) => (
        <>
          <AppHeader me={me} home="/app" settingsHref="/app/settings" />
          <div className="mx-auto w-full max-w-5xl flex-1 px-4 py-5 sm:py-8">{children}</div>
        </>
      )}
    </RoleGuard>
  );
}

export function DoctorShell({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard role="doctor">
      {(me) => (
        <>
          <AppHeader
            me={me}
            home="/doctor"
            settingsHref="/doctor/profile"
            badge={
              <Badge variant="secondary" className="hidden gap-1 sm:inline-flex">
                <Stethoscope className="size-3" /> Doctor portal
              </Badge>
            }
          >
            <DoctorNav />
          </AppHeader>
          <div className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</div>
        </>
      )}
    </RoleGuard>
  );
}

export function AdminShell({ children }: { children: React.ReactNode }) {
  return (
    <RoleGuard role="admin">
      {(me) => (
        <>
          <AppHeader
            me={me}
            home="/admin"
            badge={
              <Badge variant="secondary" className="hidden gap-1 sm:inline-flex">
                <ShieldCheck className="size-3" /> Admin
              </Badge>
            }
          >
            <SectionNav
              label="Admin console"
              links={[
                { href: "/admin", label: "Overview", exact: true },
                { href: "/admin/doctors", label: "Doctors" },
                { href: "/admin/activity", label: "Activity" },
                { href: "/admin/system", label: "System" },
                { href: "/admin/users", label: "Users" },
              ]}
            />
          </AppHeader>
          <div className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</div>
        </>
      )}
    </RoleGuard>
  );
}

function DoctorNav() {
  const pathname = usePathname();
  return (
    <SectionNav
      label="Doctor portal"
      links={[
        { href: "/doctor", label: "Patients", active: pathname === "/doctor" || pathname.startsWith("/doctor/patients") },
        { href: "/doctor/requests", label: "Requests" },
        { href: "/doctor/profile", label: "Profile" },
      ]}
    />
  );
}

function SectionNav({
  label,
  links,
}: {
  label: string;
  links: { href: string; label: string; exact?: boolean; active?: boolean }[];
}) {
  const pathname = usePathname();
  return (
    <nav aria-label={label} className="ml-2 flex min-w-0 gap-1 overflow-x-auto [scrollbar-width:none]">
      {links.map((l) => {
        const active = l.active ?? (l.exact ? pathname === l.href : pathname.startsWith(l.href));
        return (
          <Link
            key={l.href}
            href={l.href}
            aria-current={active ? "page" : undefined}
            className={
              active
                ? "shrink-0 rounded-md bg-accent px-2.5 py-1.5 text-sm font-medium"
                : "shrink-0 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            }
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}
