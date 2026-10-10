"use client";

import { LogOut, Settings } from "lucide-react";
import { useRouter } from "next/navigation";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLogout } from "@/lib/hooks/auth";
import type { Me } from "@/lib/types";

function initials(name: string) {
  return name
    .replace(/^Dr\.?\s+/i, "")
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function UserMenu({ me, settingsHref }: { me: Me; settingsHref?: string }) {
  const logout = useLogout();
  const router = useRouter();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="rounded-full focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        aria-label="Account menu"
      >
        <Avatar className="size-8">
          {me.avatar_url && <AvatarImage src={me.avatar_url} alt="" />}
          <AvatarFallback className="bg-secondary text-xs text-secondary-foreground">
            {initials(me.name)}
          </AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="font-normal">
            <p className="truncate text-sm font-medium text-foreground">{me.name}</p>
            <p className="truncate text-xs text-muted-foreground">{me.email}</p>
          </DropdownMenuLabel>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        {settingsHref && (
          <DropdownMenuItem onClick={() => router.push(settingsHref)}>
            <Settings /> Settings
          </DropdownMenuItem>
        )}
        <DropdownMenuItem onClick={() => logout.mutate()}>
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
