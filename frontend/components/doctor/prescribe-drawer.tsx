"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertOctagon, AlertTriangle, CheckCircle2, Loader2, Pill, Printer, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button, buttonVariants } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Drug {
  label: string;
  brand: string | null;
  generic: string;
  form: string | null;
  strengths: string[];
}
interface CheckAlert {
  type: string;
  severity: "critical" | "warning" | "info";
  title: string;
  clinical_text: string;
  redacted: boolean;
}
interface CheckOut {
  draft: { generic: string; brand: string | null; display: string };
  alerts: CheckAlert[];
}

const FREQUENCIES = ["1-0-1", "1-0-0", "0-0-1", "1-1-1", "0-1-0", "SOS"];

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function PrescribeDrawer({ profileId, open, onOpenChange }: { profileId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto sm:max-w-lg">
        <SheetHeader className="border-b">
          <SheetTitle className="flex items-center gap-2">
            <Pill className="size-5 text-primary" /> Prescribe
          </SheetTitle>
          <SheetDescription>Safety checks run against the whole record as you type.</SheetDescription>
        </SheetHeader>
        {open && <PrescribeForm profileId={profileId} onDone={() => onOpenChange(false)} />}
      </SheetContent>
    </Sheet>
  );
}

function PrescribeForm({ profileId, onDone }: { profileId: string; onDone: () => void }) {
  const qc = useQueryClient();
  const [drug, setDrug] = useState("");
  const [picked, setPicked] = useState<Drug | null>(null);
  const [strength, setStrength] = useState("");
  const [frequency, setFrequency] = useState("1-0-1");
  const [duration, setDuration] = useState("");
  const [instructions, setInstructions] = useState("");
  const [override, setOverride] = useState("");
  const [saved, setSaved] = useState<{ display: string; pdf_url: string } | null>(null);

  const dq = useDebounced(drug, 250);
  const search = useQuery({
    queryKey: ["drugs", dq],
    queryFn: () => api.get<Drug[]>(`/drugs?q=${encodeURIComponent(dq)}`),
    enabled: dq.length >= 2 && !picked,
  });
  const draft = { drug, strength: strength || null, frequency, duration_days: duration ? Number(duration) : null };
  const debouncedDraft = useDebounced(JSON.stringify(draft), 400);
  const check = useQuery({
    queryKey: ["rx-check", profileId, debouncedDraft],
    queryFn: () => api.post<CheckOut>(`/profiles/${profileId}/prescriptions/check`, JSON.parse(debouncedDraft)),
    enabled: drug.trim().length >= 3,
    placeholderData: (prev) => prev,
  });
  const alerts = drug.trim().length >= 3 ? check.data?.alerts ?? [] : [];
  const critical = alerts.some((a) => a.severity === "critical");

  const save = useMutation({
    mutationFn: () =>
      api.post<{ display: string; pdf_url: string }>(`/profiles/${profileId}/prescriptions`, {
        ...draft,
        instructions: instructions || null,
        override_reason: critical ? override : null,
      }),
    onSuccess: (r) => {
      setSaved(r);
      toast.success(`Prescribed ${r.display}`);
      qc.invalidateQueries({ queryKey: ["record", profileId] });
      qc.invalidateQueries({ queryKey: ["alerts", profileId] });
      qc.invalidateQueries({ queryKey: ["profile", profileId] });
    },
    onError: (e) => toast.error(e instanceof ApiError && e.status === 409 ? "A critical alert needs an override reason" : e.message),
  });

  if (saved)
    return (
      <div className="flex flex-col items-center gap-3 p-8 text-center">
        <CheckCircle2 className="size-10 text-success" />
        <p className="font-semibold">{saved.display} prescribed</p>
        <p className="text-sm text-muted-foreground">Added to the record as a FHIR MedicationRequest signed by you.</p>
        <a href={saved.pdf_url} target="_blank" rel="noreferrer" className={buttonVariants({ variant: "outline" })}>
          <Printer /> Print prescription
        </a>
        <Button variant="ghost" onClick={onDone}>
          Close
        </Button>
      </div>
    );

  return (
    <form
      className="space-y-4 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <Field label="Medicine (brand or generic)" htmlFor="rx-drug">
        <div className="relative">
          <Input
            id="rx-drug"
            value={drug}
            autoComplete="off"
            placeholder="e.g. Novamox 500 or amoxicillin"
            onChange={(e) => {
              setDrug(e.target.value);
              setPicked(null);
            }}
          />
          {!!search.data?.length && !picked && drug.length >= 2 && (
            <ul className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-lg border bg-popover shadow-md" role="listbox">
              {search.data.map((d) => (
                <li key={d.label}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-muted"
                    onClick={() => {
                      setPicked(d);
                      setDrug(d.label);
                      setStrength(d.strengths[0] ?? "");
                    }}
                  >
                    <span>
                      <span className="font-medium">{d.label}</span>
                      {d.brand && <span className="text-muted-foreground"> · {d.generic}</span>}
                    </span>
                    {d.form && <span className="text-xs text-muted-foreground">{d.form}</span>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Strength" htmlFor="rx-strength">
          {picked?.strengths.length ? (
            <NativeSelect id="rx-strength" value={strength} onChange={(e) => setStrength(e.target.value)}>
              {picked.strengths.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </NativeSelect>
          ) : (
            <Input id="rx-strength" value={strength} onChange={(e) => setStrength(e.target.value)} placeholder="500 mg" />
          )}
        </Field>
        <Field label="Duration (days)" htmlFor="rx-duration" hint="Empty = long-term">
          <Input id="rx-duration" type="number" min={1} value={duration} onChange={(e) => setDuration(e.target.value)} />
        </Field>
      </div>
      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">How often (morning-afternoon-night)</legend>
        <div className="flex flex-wrap gap-1.5">
          {FREQUENCIES.map((f) => (
            <button
              type="button"
              key={f}
              aria-pressed={frequency === f}
              onClick={() => setFrequency(f)}
              className={cn(
                "rounded-lg border px-3 py-1.5 font-mono text-sm",
                frequency === f ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-muted",
              )}
            >
              {f}
            </button>
          ))}
          <Input aria-label="Custom frequency" className="w-24 font-mono" value={FREQUENCIES.includes(frequency) ? "" : frequency} placeholder="custom" onChange={(e) => setFrequency(e.target.value)} />
        </div>
      </fieldset>
      <Field label="Instructions" htmlFor="rx-instr">
        <Input id="rx-instr" value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="after food" />
      </Field>

      <section aria-live="polite" className="space-y-2">
        <p className="flex items-center gap-2 text-sm font-medium">
          Safety check {check.isFetching && <Loader2 className="size-3.5 animate-spin text-muted-foreground" />}
        </p>
        {drug.trim().length < 3 ? (
          <p className="text-sm text-muted-foreground">Start typing a medicine.</p>
        ) : !alerts.length && check.isSuccess ? (
          <p className="flex items-center gap-2 rounded-lg bg-success-soft px-3 py-2 text-sm">
            <ShieldCheck className="size-4 text-success" /> No conflicts found for {check.data?.draft.display}
            {check.data?.draft.brand ? ` (${check.data.draft.brand})` : ""}
          </p>
        ) : (
          alerts.map((a, i) => (
            <div
              key={i}
              className={cn(
                "rounded-lg border px-3 py-2 text-sm",
                a.severity === "critical" ? "border-critical/50 bg-critical-soft" : "border-warning/50 bg-warning-soft",
              )}
            >
              <p className="flex items-center gap-1.5 font-semibold">
                {a.severity === "critical" ? <AlertOctagon className="size-4 text-critical" /> : <AlertTriangle className="size-4 text-warning" />}
                {a.severity === "critical" ? "Critical" : "Warning"}: {a.title}
              </p>
              <p className="mt-1 text-xs">{a.clinical_text}</p>
            </div>
          ))
        )}
        {critical && (
          <Field label="Override reason (required to prescribe despite a critical alert)" htmlFor="rx-override">
            <Textarea id="rx-override" value={override} onChange={(e) => setOverride(e.target.value)} rows={2} />
          </Field>
        )}
      </section>

      <Button type="submit" size="lg" className="w-full" variant={critical ? "destructive" : "default"} disabled={!drug.trim() || save.isPending || (critical && !override.trim())}>
        {save.isPending && <Loader2 className="animate-spin" />}
        {critical ? "Prescribe anyway (override recorded)" : "Prescribe"}
      </Button>
    </form>
  );
}
