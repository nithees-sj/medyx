"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { Bell } from "lucide-react";
import { useRouter } from "next/navigation";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api } from "@/lib/api";
import type { NotificationItem } from "@/lib/types";
import { cn } from "@/lib/utils";

export function NotificationBell() {
  const qc = useQueryClient();
  const router = useRouter();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<{ unread: number; items: NotificationItem[] }>("/notifications"),
    refetchInterval: 15_000,
  });
  const markRead = useMutation({
    mutationFn: (id: string) => api.post(`/notifications/${id}/read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const markAll = useMutation({
    mutationFn: () => api.post("/notifications/read-all"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const unread = data?.unread ?? 0;

  return (
    <Popover>
      <PopoverTrigger
        className="relative inline-flex size-9 items-center justify-center rounded-lg hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
      >
        <Bell className="size-5" />
        {unread > 0 && (
          <span className="absolute top-1 right-1 flex min-w-4 items-center justify-center rounded-full bg-critical px-1 text-[10px] font-semibold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="flex items-center justify-between border-b px-3 py-2">
          <p className="text-sm font-medium">Notifications</p>
          {unread > 0 && (
            <button className="text-xs text-primary hover:underline" onClick={() => markAll.mutate()}>
              Mark all read
            </button>
          )}
        </div>
        <ul className="max-h-96 overflow-y-auto">
          {!data?.items.length && (
            <li className="px-3 py-6 text-center text-sm text-muted-foreground">You&apos;re all caught up.</li>
          )}
          {data?.items.map((n) => (
            <li key={n.id}>
              <button
                className={cn(
                  "w-full border-b px-3 py-2.5 text-left last:border-0 hover:bg-muted/60",
                  !n.read_at && "bg-accent/40",
                )}
                onClick={() => {
                  if (!n.read_at) markRead.mutate(n.id);
                  if (n.link) router.push(n.link);
                }}
              >
                <p className="text-sm font-medium">{n.title}</p>
                {n.body && <p className="line-clamp-2 text-xs text-muted-foreground">{n.body}</p>}
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}
                </p>
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
