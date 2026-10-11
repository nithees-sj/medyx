"use client";

import { useQuery } from "@tanstack/react-query";
import { Search, Users } from "lucide-react";
import { useDeferredValue, useState } from "react";

import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { api } from "@/lib/api";
import { fmtInstant } from "@/lib/format";
import type { UserRow } from "@/lib/hooks/admin";

const PAGE = 50;

export function UsersView() {
  const [q, setQ] = useState("");
  const [role, setRole] = useState("");
  const [page, setPage] = useState(0);
  const query = useDeferredValue(q);
  const users = useQuery({
    queryKey: ["admin", "users", query, role, page],
    queryFn: () => {
      const p = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
      if (query.trim()) p.set("q", query.trim());
      if (role) p.set("role", role);
      return api.get<{ total: number; items: UserRow[] }>(`/admin/users?${p}`);
    },
    placeholderData: (prev) => prev,
  });
  const total = users.data?.total ?? 0;

  return (
    <div className="space-y-5">
      <PageHeader title="Users" description="Accounts and roles. Health profiles are counted, never opened." />
      <div className="flex flex-wrap gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Search by name or email"
            placeholder="Search name or email"
            className="pl-8"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(0);
            }}
          />
        </div>
        <NativeSelect
          aria-label="Role"
          value={role}
          onChange={(e) => {
            setRole(e.target.value);
            setPage(0);
          }}
        >
          <option value="">All roles</option>
          <option value="patient">Patients & caregivers</option>
          <option value="doctor">Doctors</option>
          <option value="admin">Admins</option>
          <option value="none">Not onboarded</option>
        </NativeSelect>
      </div>
      {users.isLoading ? (
        <LoadingState rows={6} />
      ) : users.isError ? (
        <ErrorState error={users.error} onRetry={() => users.refetch()} />
      ) : !users.data?.items.length ? (
        <EmptyState icon={Users} title="No users match" />
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">User</th>
                <th className="px-4 py-2 font-medium">Role</th>
                <th className="px-4 py-2 text-right font-medium">Profiles</th>
                <th className="px-4 py-2 font-medium">Joined</th>
                <th className="px-4 py-2 font-medium">Last sign-in</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {users.data.items.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-2">
                    <p className="font-medium">{u.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {u.email}
                      {u.sign_in === "demo" && " · demo account"}
                    </p>
                  </td>
                  <td className="px-4 py-2">
                    <Badge variant={u.role ? "secondary" : "outline"}>{u.role ?? "not onboarded"}</Badge>
                    {u.doctor_status && <span className="ml-1.5 text-xs text-muted-foreground">{u.doctor_status}</span>}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{u.role === "patient" ? u.profiles : ""}</td>
                  <td className="px-4 py-2 text-muted-foreground">{fmtInstant(u.created_at, "d MMM yyyy")}</td>
                  <td className="px-4 py-2 text-muted-foreground">{u.last_login_at ? fmtInstant(u.last_login_at, "d MMM, h:mm a") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {total > PAGE && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            {page * PAGE + 1}–{Math.min(total, (page + 1) * PAGE)} of {total}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
              Previous
            </Button>
            <Button variant="outline" size="sm" disabled={(page + 1) * PAGE >= total} onClick={() => setPage((p) => p + 1)}>
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
