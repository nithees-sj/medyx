"use client";

import { useQuery } from "@tanstack/react-query";
import { NotebookPen, Plus } from "lucide-react";
import { useState } from "react";

import { NoteDialog } from "@/components/doctor/note-dialog";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { fmtInstant } from "@/lib/format";

interface Note {
  id: string;
  title: string;
  body: string;
  author: string | null;
  created_at: string;
}

export function NotesTab({ profileId, canWrite }: { profileId: string; canWrite: boolean }) {
  const notes = useQuery({ queryKey: ["notes", profileId], queryFn: () => api.get<Note[]>(`/profiles/${profileId}/notes`) });
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <div className="space-y-3">
      {canWrite && (
        <Button size="sm" onClick={() => setDraft("")}>
          <Plus /> New note
        </Button>
      )}
      {notes.isLoading ? (
        <LoadingState rows={2} />
      ) : notes.isError ? (
        <ErrorState error={notes.error} onRetry={() => notes.refetch()} />
      ) : !notes.data?.length ? (
        <EmptyState icon={NotebookPen} title="No clinical notes" description="Save a copilot draft or write a visit note." />
      ) : (
        notes.data.map((n) => (
          <article key={n.id} className="rounded-xl border bg-card p-4">
            <p className="font-medium">{n.title}</p>
            <p className="text-xs text-muted-foreground">
              {n.author} · {fmtInstant(n.created_at)}
            </p>
            <p className="mt-2 text-sm whitespace-pre-wrap">{n.body}</p>
          </article>
        ))
      )}
      <NoteDialog profileId={profileId} draft={draft} onClose={() => setDraft(null)} />
    </div>
  );
}
