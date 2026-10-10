"use client";

import { profileLabel } from "@/lib/hooks/profiles";
import type { Profile } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ProfileSwitcher({
  profiles,
  selectedId,
  onSelect,
}: {
  profiles: Profile[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div role="tablist" aria-label="Health profiles" className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
      {profiles.map((p) => {
        const active = p.id === selectedId;
        return (
          <button
            key={p.id}
            role="tab"
            aria-selected={active}
            onClick={() => onSelect(p.id)}
            className={cn(
              "flex shrink-0 items-center gap-2 rounded-full border py-1 pr-3 pl-1 text-sm transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
              active ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-muted",
            )}
          >
            <span
              className={cn(
                "flex size-7 items-center justify-center rounded-full text-xs font-semibold",
                active ? "bg-white/20" : "bg-secondary text-secondary-foreground",
              )}
            >
              {p.display_name[0]}
            </span>
            {profileLabel(p)}
            {p.critical_alerts > 0 && (
              <span className="size-2 rounded-full bg-critical ring-2 ring-white" aria-label="critical alert" />
            )}
          </button>
        );
      })}
    </div>
  );
}
