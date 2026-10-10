"use client";

import { Download, Loader2, LogOut } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { AddProfileDialog } from "@/components/patient/add-profile-dialog";
import { ErrorState, LoadingState, PageHeader } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useLogout, useMe } from "@/lib/hooks/auth";
import { profileLabel, useProfiles } from "@/lib/hooks/profiles";
import type { Profile } from "@/lib/types";

export function SettingsView() {
  const { data: me } = useMe();
  const profiles = useProfiles();
  const logout = useLogout();
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description={me ? `Signed in as ${me.email}` : undefined} />
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle className="text-base">Health profiles</CardTitle>
            <CardDescription>Yourself and the family members you manage.</CardDescription>
          </div>
          <AddProfileDialog />
        </CardHeader>
        <CardContent>
          {profiles.isLoading ? (
            <LoadingState rows={2} />
          ) : profiles.isError ? (
            <ErrorState error={profiles.error} onRetry={() => profiles.refetch()} />
          ) : (
            <ul className="divide-y">
              {profiles.data?.map((p) => (
                <ProfileRow key={p.id} profile={p} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sign out</CardTitle>
          <CardDescription>Your record stays safe in HealthThread.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={() => logout.mutate()}>
            <LogOut /> Sign out
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function ProfileRow({ profile: p }: { profile: Profile }) {
  const [busy, setBusy] = useState(false);
  const exportBundle = async () => {
    setBusy(true);
    try {
      const bundle = await api.get<{ entry: unknown[] }>(`/profiles/${p.id}/export`);
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/fhir+json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${p.display_name.replace(/\s+/g, "_")}_${p.healththread_id}_fhir.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`Exported ${bundle.entry.length} FHIR resources`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div>
        <p className="font-medium">{p.display_name}</p>
        <p className="text-xs text-muted-foreground">
          {profileLabel(p)} · {p.age} yrs · <span className="font-mono">{p.healththread_id}</span>
        </p>
      </div>
      <Button variant="outline" size="sm" onClick={exportBundle} disabled={busy}>
        {busy ? <Loader2 className="animate-spin" /> : <Download />} Export as FHIR Bundle
      </Button>
    </li>
  );
}
