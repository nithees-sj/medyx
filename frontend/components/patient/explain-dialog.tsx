"use client";

import { useMutation } from "@tanstack/react-query";
import { Languages, Loader2 } from "lucide-react";
import { useState } from "react";

import { CitedText } from "@/components/copilot/cited-text";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/native-select";
import { api } from "@/lib/api";
import type { Citation } from "@/lib/hooks/doctor";

const LANGUAGES = ["English", "Tamil", "Hindi"] as const;

export function ExplainDialog({ documentId, label }: { documentId: string; label: string }) {
  const [language, setLanguage] = useState<(typeof LANGUAGES)[number]>("English");
  const explain = useMutation({
    mutationFn: () => api.post<{ text: string; citations: Citation[] }>(`/documents/${documentId}/explain`, { language }),
  });
  return (
    <Dialog onOpenChange={(o) => !o && explain.reset()}>
      <DialogTrigger render={<Button size="xs" variant="outline" />}>
        <Languages /> Explain simply
      </DialogTrigger>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Explain {label} in simple words</DialogTitle>
          <DialogDescription>Written only from what was read from this document. Tap a source to see it on the page.</DialogDescription>
        </DialogHeader>
        <div className="flex gap-2">
          <NativeSelect aria-label="Language" value={language} onChange={(e) => setLanguage(e.target.value as (typeof LANGUAGES)[number])}>
            {LANGUAGES.map((l) => (
              <option key={l}>{l}</option>
            ))}
          </NativeSelect>
          <Button onClick={() => explain.mutate()} disabled={explain.isPending}>
            {explain.isPending && <Loader2 className="animate-spin" />} Explain
          </Button>
        </div>
        {explain.isError && <p className="text-sm text-critical">{explain.error.message}</p>}
        {explain.data && <CitedText text={explain.data.text} citations={explain.data.citations} className="rounded-lg border bg-card p-3" />}
        <p className="text-xs text-muted-foreground">AI-generated explanation — not medical advice. Discuss your results with your doctor.</p>
      </DialogContent>
    </Dialog>
  );
}
