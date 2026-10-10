import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { NotificationBell } from "@/components/shell/notification-bell";
import { UserMenu } from "@/components/shell/user-menu";
import type { Me } from "@/lib/types";

export function AppHeader({
  me,
  home,
  badge,
  settingsHref,
  children,
}: {
  me: Me;
  home: string;
  badge?: React.ReactNode;
  settingsHref?: string;
  children?: React.ReactNode;
}) {
  return (
    <header className="sticky top-0 z-30 border-b bg-card/90 backdrop-blur supports-[backdrop-filter]:bg-card/75">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-3 px-4">
        <Link href={home} className="rounded-md focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
          <Logo className="[&>span]:hidden sm:[&>span]:inline" />
        </Link>
        {badge}
        <div className="flex min-w-0 flex-1 items-center gap-1">{children}</div>
        <NotificationBell />
        <UserMenu me={me} settingsHref={settingsHref} />
      </div>
    </header>
  );
}
