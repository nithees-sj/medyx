"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, Power, RefreshCw, Siren, Smartphone } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useState } from "react";
import { toast } from "sonner";

import { EmergencyCardView, type EmergencyData } from "@/components/emergency/card-preview";
import { ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { fmtInstant } from "@/lib/format";

interface Status {
  enabled: boolean;
  created_at: string | null;
  regenerated_at: string | null;
  preview: EmergencyData;
}

async function download(path: string, token: string, filename: string) {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-HT-Request": "1" },
    body: JSON.stringify({ token }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.detail ?? "Download failed");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function EmergencyView({ profileId }: { profileId: string }) {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["emergency", profileId], queryFn: () => api.get<Status>(`/profiles/${profileId}/emergency`) });
  // The card token is shown only right after it is created (the server keeps just its hash).
  const [fresh, setFresh] = useState<{ token: string; url: string } | null>(null);
  const enable = useMutation({
    mutationFn: () => api.post<{ token: string; url: string }>(`/profiles/${profileId}/emergency/enable`),
    onSuccess: (r) => {
      setFresh(r);
      qc.invalidateQueries({ queryKey: ["emergency", profileId] });
      toast.success(status.data?.enabled ? "New card created — the old QR no longer works" : "Emergency card is on");
    },
    onError: (e) => toast.error(e.message),
  });
  const disable = useMutation({
    mutationFn: () => api.post(`/profiles/${profileId}/emergency/disable`),
    onSuccess: () => {
      setFresh(null);
      qc.invalidateQueries({ queryKey: ["emergency", profileId] });
      toast.success("Emergency card turned off");
    },
  });

  if (status.isLoading) return <LoadingState rows={3} />;
  if (status.isError) return <ErrorState error={status.error} onRetry={() => status.refetch()} />;
  const s = status.data!;
  const slug = s.preview.healththread_id;

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_380px]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Siren className="size-5 text-critical" /> Emergency card
          </CardTitle>
          <CardDescription>
            Anyone who scans this QR (an ambulance crew, an ER) sees allergies, blood group, current medicines and an emergency
            contact. No lab results, no documents. You&apos;re notified every time it&apos;s opened.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!s.enabled ? (
            <Button size="lg" onClick={() => enable.mutate()} disabled={enable.isPending}>
              {enable.isPending ? <Loader2 className="animate-spin" /> : <Siren />} Turn on emergency card
            </Button>
          ) : fresh ? (
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="rounded-2xl border bg-white p-4">
                <QRCodeSVG value={fresh.url} size={200} marginSize={1} aria-label="Emergency card QR code" />
              </div>
              <p className="text-sm text-muted-foreground">Save it now. For your safety we can&apos;t show this QR again.</p>
              <div className="flex flex-wrap justify-center gap-2">
                <Button
                  onClick={() =>
                    download(`/profiles/${profileId}/emergency/wallet.pdf`, fresh.token, `emergency-card-${slug}.pdf`).catch((e) =>
                      toast.error(e.message),
                    )
                  }
                >
                  <Download /> Wallet card (PDF)
                </Button>
                <Button
                  variant="outline"
                  onClick={() =>
                    download(`/profiles/${profileId}/emergency/lockscreen.png`, fresh.token, `emergency-lockscreen-${slug}.png`).catch(
                      (e) => toast.error(e.message),
                    )
                  }
                >
                  <Smartphone /> Lock-screen image
                </Button>
              </div>
              <a href={fresh.url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">
                Open the card as a responder would see it
              </a>
            </div>
          ) : (
            <div className="space-y-2 text-sm">
              <p>
                Your card is <span className="font-medium text-success">on</span> since{" "}
                {fmtInstant(s.regenerated_at ?? s.created_at)}.
              </p>
              <p className="text-muted-foreground">
                Lost your printed card or phone? Create a new card — the old QR stops working immediately.
              </p>
            </div>
          )}
          {s.enabled && (
            <div className="flex flex-wrap gap-2 border-t pt-4">
              <Button variant="outline" size="sm" onClick={() => enable.mutate()} disabled={enable.isPending}>
                <RefreshCw /> {fresh ? "Create another new card" : "Create a new card"}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => disable.mutate()} disabled={disable.isPending}>
                <Power /> Turn off
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
      <div>
        <p className="mb-2 text-sm font-medium text-muted-foreground">What a responder sees</p>
        <div className="rounded-2xl border bg-background p-4">
          <EmergencyCardView data={s.preview} />
        </div>
      </div>
    </div>
  );
}
