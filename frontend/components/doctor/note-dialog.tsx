"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";

/** Editable draft → clinical note (stored + FHIR DocumentReference authored by the doctor). */
export function NoteDialog({ profileId, draft, onClose }: { profileId: string; draft: string | null; onClose: () => void }) {
  return (
    <Dialog open={draft !== null} onOpenChange={(o) => !o && onClose()}>
      {draft !== null && <NoteForm key={draft} profileId={profileId} draft={draft} onClose={onClose} />}
    </Dialog>
  );
}

function NoteForm({ profileId, draft, onClose }: { profileId: string; draft: string; onClose: () => void }) {
  const firstLine = draft.split("\n").find((l) => l.trim())?.replace(/\[[^\]]+\]/g, "").slice(0, 80) ?? "Clinical note";
  const [title, setTitle] = useState(/letter|summary|referral/i.test(firstLine) ? firstLine.trim() : "Visit note");
  const [body, setBody] = useState(draft);
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => api.post(`/profiles/${profileId}/notes`, { title, body }),
    onSuccess: () => {
      toast.success("Saved to the record as a clinical note");
      qc.invalidateQueries({ queryKey: ["notes", profileId] });
      onClose();
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <DialogContent className="sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>Save as clinical note</DialogTitle>
        <DialogDescription>Edit the draft before saving. It&apos;s stored as a FHIR DocumentReference authored by you.</DialogDescription>
      </DialogHeader>
      <Field label="Title" htmlFor="note-title">
        <Input id="note-title" value={title} onChange={(e) => setTitle(e.target.value)} />
      </Field>
      <Field label="Note" htmlFor="note-body">
        <Textarea id="note-body" value={body} onChange={(e) => setBody(e.target.value)} rows={14} className="font-mono text-xs" />
      </Field>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={() => save.mutate()} disabled={!title.trim() || !body.trim() || save.isPending}>
          {save.isPending && <Loader2 className="animate-spin" />} Save note
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
