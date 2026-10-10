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
              <Badge variant="secondary" className="gap-1">
                <ShieldCheck className="size-3" /> Admin
              </Badge>
            }
          />
          <div className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</div>
        </>
      )}
    </RoleGuard>
  );
}

function DoctorNav() {
  const pathname = usePathname();
  const links = [
    { href: "/doctor", label: "Patients" },
    { href: "/doctor/requests", label: "Requests" },
    { href: "/doctor/profile", label: "Profile" },
  ];
  return (
    <nav aria-label="Doctor portal" className="ml-2 flex gap-1">
      {links.map((l) => {
        const active = l.href === "/doctor" ? pathname === "/doctor" || pathname.startsWith("/doctor/patients") : pathname.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            aria-current={active ? "page" : undefined}
            className={
              active
                ? "rounded-md bg-accent px-2.5 py-1.5 text-sm font-medium"
                : "rounded-md px-2.5 py-1.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            }
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}
