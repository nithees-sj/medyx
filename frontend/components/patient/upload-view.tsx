"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera, Check, CloudUpload, FileText, Loader2, X } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { buttonVariants } from "@/components/ui/button";
import { api } from "@/lib/api";
import { countsSummary } from "@/lib/format";
import { recordKeys, useDocuments } from "@/lib/hooks/record";
import type { DocumentRow, UploadResult } from "@/lib/record-types";
import { cn } from "@/lib/utils";

export const STAGES = [
  "Uploading",
  "Reading document",
  "Extracting with AI",
  "Normalising codes & units",
  "Merging with existing record",
  "Saving to FHIR",
  "Running safety checks",
  "Done",
];

const ACCEPT = "application/pdf,image/jpeg,image/png";

export function UploadView({ profileId, base }: { profileId: string; base?: string }) {
  const [results, setResults] = useState<UploadResult[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const tracking = results.some((r) => r.document && !r.duplicate);
  const docs = useDocuments(profileId, { poll: tracking });

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      return api.post<UploadResult[]>(`/profiles/${profileId}/documents`, form);
    },
    onSuccess: (r) => {
      setResults((prev) => [...r, ...prev]);
      qc.invalidateQueries({ queryKey: recordKeys.docs(profileId) });
    },
    onError: (e) => toast.error(e.message),
  });

  const pick = (list: FileList | null) => {
    const files = Array.from(list ?? []);
    if (!files.length) return;
    const tooBig = files.filter((f) => f.size > 15 * 1024 * 1024);
    if (tooBig.length) toast.error(`${tooBig.map((f) => f.name).join(", ")}: larger than 15 MB`);
    const ok = files.filter((f) => f.size <= 15 * 1024 * 1024);
    if (ok.length) upload.mutate(ok);
  };

  const live = new Map((docs.data ?? []).map((d) => [d.id, d]));
  const tracked = results.map((r) => ({ ...r, live: r.document ? live.get(r.document.id) ?? r.document : null }));
  const finished = tracked.filter((t) => t.live && ["done", "needs_review", "failed"].includes(t.live.status));
  const allFinished = tracked.length > 0 && tracked.every((t) => !t.live || finished.includes(t) || t.duplicate);
  const needsReview = tracked.some((t) => t.live?.status === "needs_review");

  return (
    <div className="space-y-5">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          pick(e.dataTransfer.files);
        }}
        className={cn(
          "flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed bg-card px-6 py-10 text-center transition-colors",
          dragging ? "border-primary bg-accent/50" : "border-border",
        )}
      >
        <CloudUpload className="size-10 text-primary" />
        <div>
          <p className="font-medium">Drop prescriptions, lab reports or discharge summaries</p>
          <p className="text-sm text-muted-foreground">PDF, JPG or PNG · up to 15 MB and 20 pages each · many at once</p>
        </div>
        <div className="flex flex-wrap justify-center gap-2">
          <button className={buttonVariants({ size: "lg" })} onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
            {upload.isPending ? <Loader2 className="animate-spin" /> : <FileText />} Choose files
          </button>
          <button
            className={buttonVariants({ size: "lg", variant: "outline" })}
            onClick={() => cameraRef.current?.click()}
            disabled={upload.isPending}
          >
            <Camera /> Take a photo
          </button>
        </div>
        <input ref={fileRef} type="file" accept={ACCEPT} multiple hidden onChange={(e) => pick(e.target.files)} />
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={(e) => pick(e.target.files)} />
      </div>

      {tracked.length > 0 && (
        <section className="space-y-2" aria-live="polite">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-muted-foreground">
              {allFinished ? "All done" : `Processing ${tracked.filter((t) => t.live && !finished.includes(t)).length} of ${tracked.length}`}
            </h2>
            {allFinished && base && (
              <div className="flex gap-2">
                {needsReview && (
                  <Link href={`${base}/review`} className={buttonVariants({ size: "sm", variant: "outline" })}>
                    Review items
                  </Link>
                )}
                <Link href={`${base}/timeline`} className={buttonVariants({ size: "sm" })}>
                  View timeline
                </Link>
              </div>
            )}
          </div>
          <ul className="space-y-2">
            {tracked.map((t, i) => (
              <UploadRow key={`${t.filename}-${i}`} result={t} doc={t.live} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function UploadRow({ result, doc }: { result: UploadResult; doc: DocumentRow | null }) {
  if (result.error)
    return (
      <li className="flex items-start gap-3 rounded-xl border border-critical/30 bg-critical-soft p-3 text-sm">
        <X className="mt-0.5 size-4 text-critical" />
        <span>
          <span className="font-medium">{result.filename}</span> — {result.error}
        </span>
      </li>
    );
  if (result.duplicate)
    return (
      <li className="flex items-start gap-3 rounded-xl border bg-card p-3 text-sm">
        <Check className="mt-0.5 size-4 text-muted-foreground" />
        <span>
          <span className="font-medium">{result.filename}</span> is already in this record ({doc?.label}). Skipped.
        </span>
      </li>
    );
  if (!doc) return null;
  const idx = doc.status === "failed" ? -1 : Math.max(0, STAGES.indexOf(doc.stage));
  const done = doc.status === "done" || doc.status === "needs_review";
  return (
    <li className="rounded-xl border bg-card p-3 sm:p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 truncate text-sm font-medium">
          <span className="text-muted-foreground">{doc.label}</span> · {result.filename}
        </p>
        <span className="shrink-0 text-xs text-muted-foreground">
          {doc.status === "failed" ? "Failed" : done ? (doc.status === "needs_review" ? "Needs review" : "Done") : doc.stage}
        </span>
      </div>
      {doc.status === "failed" ? (
        <p className="mt-2 text-sm text-critical">{doc.error}</p>
      ) : (
        <>
          <ol className="mt-3 flex gap-1" aria-label="Progress">
            {STAGES.map((s, i) => (
              <li
                key={s}
                title={s}
                className={cn(
                  "h-1.5 flex-1 rounded-full transition-colors",
                  i < idx || done ? "bg-primary" : i === idx ? "animate-pulse bg-primary/60" : "bg-muted",
                )}
              />
            ))}
          </ol>
          <p className="mt-2 text-xs text-muted-foreground">
            {done ? countsSummary(doc.result_counts) + (doc.result_counts?.pending ? ` · ${doc.result_counts.pending} to review` : "") : `${doc.stage}…`}
          </p>
        </>
      )}
    </li>
  );
}
