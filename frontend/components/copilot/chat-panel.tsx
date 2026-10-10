"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bot, Loader2, NotebookPen, Send, Sparkles, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { CitedText } from "@/components/copilot/cited-text";
import { NoteDialog } from "@/components/doctor/note-dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { type ChatMsg, type Citation, useChatHistory } from "@/lib/hooks/doctor";
import { cn } from "@/lib/utils";

export const QUICK_PROMPTS = [
  "Summarise the last 6 months",
  "All medication changes with reasons",
  "Any safety concerns?",
  "Draft a referral letter to cardiology",
];

export function ChatPanel({ profileId, canWrite, patientName }: { profileId: string; canWrite: boolean; patientName: string }) {
  const history = useChatHistory(profileId);
  const qc = useQueryClient();
  const [local, setLocal] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [noteDraft, setNoteDraft] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const messages = [...(history.data ?? []), ...local];

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, local]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setInput("");
    const now = new Date().toISOString();
    const assistant: ChatMsg = { id: `a-${now}`, role: "assistant", content: "", citations: [], created_at: now, pending: true };
    setLocal([{ id: `u-${now}`, role: "user", content: q, citations: [], created_at: now }, assistant]);
    const update = (patch: Partial<ChatMsg>) => setLocal((l) => l.map((m) => (m.id === assistant.id ? { ...m, ...patch } : m)));
    try {
      const res = await fetch(`/api/profiles/${profileId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-HT-Request": "1", Accept: "text/event-stream" },
        body: JSON.stringify({ message: q }),
      });
      if (!res.ok || !res.body) {
        const detail = (await res.json().catch(() => ({})))?.detail;
        throw new Error(typeof detail === "string" ? detail : `Request failed (${res.status})`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let text = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const raw of events) {
          const line = raw.trim();
          if (!line.startsWith("data: ")) continue;
          const ev = JSON.parse(line.slice(6)) as { type: string; text?: string; citations?: Citation[]; message?: string };
          if (ev.type === "delta" && ev.text) {
            text += ev.text;
            update({ content: text });
          } else if (ev.type === "done") {
            update({ citations: ev.citations ?? [], pending: false });
          } else if (ev.type === "error") {
            update({ pending: false, error: ev.message });
          }
        }
      }
      await qc.invalidateQueries({ queryKey: ["chat", profileId] });
      setLocal([]);
    } catch (e) {
      update({ pending: false, error: e instanceof Error ? e.message : "Something went wrong" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <Sparkles className="size-4 text-primary" />
        <p className="text-sm font-semibold">Ask the record</p>
        <span className="ml-auto text-[11px] text-muted-foreground">Answers cite their sources</span>
      </div>
      <div ref={scroller} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4" aria-live="polite">
        {history.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading conversation…</p>
        ) : messages.length === 0 ? (
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>
              Ask anything about {patientName.split(" ")[0]}&apos;s record. Every fact comes with a link to the page it was read from.
            </p>
          </div>
        ) : (
          messages.map((m) => (
            <div key={m.id} className={cn("flex gap-2.5", m.role === "user" && "flex-row-reverse")}>
              <span
                className={cn(
                  "mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full",
                  m.role === "user" ? "bg-secondary text-secondary-foreground" : "bg-primary text-primary-foreground",
                )}
              >
                {m.role === "user" ? <User className="size-3.5" /> : <Bot className="size-3.5" />}
              </span>
              <div
                className={cn(
                  "max-w-[88%] rounded-2xl px-3.5 py-2.5",
                  m.role === "user" ? "bg-secondary text-sm" : "border bg-card",
                )}
              >
                {m.role === "user" ? (
                  <p className="text-sm whitespace-pre-wrap">{m.content}</p>
                ) : m.error ? (
                  <p className="text-sm text-critical">{m.error}</p>
                ) : (
                  <>
                    {m.content ? (
                      <CitedText text={m.content} citations={m.citations} pending={m.pending} />
                    ) : (
                      <p className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="size-3.5 animate-spin" /> Reading the record…
                      </p>
                    )}
                    {!m.pending && canWrite && m.content.length > 200 && (
                      <Button variant="ghost" size="xs" className="mt-2" onClick={() => setNoteDraft(m.content)}>
                        <NotebookPen /> Save as clinical note
                      </Button>
                    )}
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>
      <div className="space-y-2 border-t p-3">
        <div className="flex flex-wrap gap-1.5">
          {QUICK_PROMPTS.map((p) => (
            <button
              key={p}
              disabled={busy}
              onClick={() => ask(p)}
              className="rounded-full border bg-card px-2.5 py-1 text-xs hover:border-primary/50 hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50"
            >
              {p}
            </button>
          ))}
        </div>
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
        >
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                ask(input);
              }
            }}
            placeholder="When did kidney function start declining?"
            rows={2}
            className="min-h-0 resize-none"
            aria-label="Ask a question about this record"
          />
          <Button type="submit" size="icon" disabled={busy || !input.trim()} aria-label="Send">
            {busy ? <Loader2 className="animate-spin" /> : <Send />}
          </Button>
        </form>
        <p className="text-[10px] text-muted-foreground">Decision support only — no diagnoses or orders. Verify against the source.</p>
      </div>
      <NoteDialog profileId={profileId} draft={noteDraft} onClose={() => setNoteDraft(null)} />
    </div>
  );
}
