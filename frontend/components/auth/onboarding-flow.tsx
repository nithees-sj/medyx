"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, HeartHandshake, Loader2, Stethoscope } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { RoleGuard } from "@/components/auth/role-guard";
import { Logo } from "@/components/brand/logo";
import {
  emptyProfile,
  fieldErrors,
  ProfileFields,
  type ProfileFormValue,
  toProfilePayload,
} from "@/components/profile/profile-form";
import { CouncilList } from "@/components/doctor/verification-panel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { api, ApiError } from "@/lib/api";
import { safeNext, useAuthConfig, useLogout } from "@/lib/hooks/auth";
import type { LoginResult, Me } from "@/lib/types";
import { cn } from "@/lib/utils";

type Step = "role" | "patient" | "doctor";

export function OnboardingFlow() {
  return <RoleGuard role="onboarding">{(me) => <Flow me={me} />}</RoleGuard>;
}

function Flow({ me }: { me: Me }) {
  const [step, setStep] = useState<Step>("role");
  const logout = useLogout();
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Logo />
        <Button variant="ghost" size="sm" onClick={() => logout.mutate()}>
          Sign out
        </Button>
      </div>
      {step === "role" && <RoleChoice name={me.name} onPick={setStep} />}
      {step === "patient" && <PatientForm me={me} onBack={() => setStep("role")} />}
      {step === "doctor" && <DoctorForm me={me} onBack={() => setStep("role")} />}
    </div>
  );
}

function RoleChoice({ name, onPick }: { name: string; onPick: (s: Step) => void }) {
  const options = [
    {
      step: "patient" as const,
      icon: HeartHandshake,
      title: "I'm a patient or family caregiver",
      body: "Gather your own records, or a parent's or child's, into one place and share them safely.",
    },
    {
      step: "doctor" as const,
      icon: Stethoscope,
      title: "I'm a doctor",
      body: "See records that patients share with you, with safety checks and a cited copilot.",
    },
  ];
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Welcome, {name.split(" ")[0]}</h1>
        <p className="text-muted-foreground">How will you use HealthThread?</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {options.map((o) => (
          <button
            key={o.step}
            onClick={() => onPick(o.step)}
            className="group flex flex-col gap-3 rounded-xl border bg-card p-5 text-left transition-colors hover:border-primary/50 hover:bg-accent/40 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            <o.icon className="size-7 text-primary" />
            <span className="font-medium">{o.title}</span>
            <span className="text-sm text-muted-foreground">{o.body}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function useFinish() {
  const router = useRouter();
  const qc = useQueryClient();
  const next = safeNext(useSearchParams().get("next"));
  return (r: LoginResult) => {
    qc.setQueryData(["me"], r.user);
    qc.invalidateQueries({ queryKey: ["profiles"] });
    router.replace(next ?? r.redirect);
  };
}

function PatientForm({ me, onBack }: { me: Me; onBack: () => void }) {
  const [name, setName] = useState(me.name);
  const [forWhom, setForWhom] = useState<"self" | "other">("self");
  const [profile, setProfile] = useState<ProfileFormValue>({ ...emptyProfile, display_name: me.name });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const finish = useFinish();

  const submit = useMutation({
    mutationFn: () =>
      api.post<LoginResult>("/onboarding/patient", {
        name,
        profile: toProfilePayload({
          ...profile,
          relationship: forWhom === "self" ? "self" : profile.relationship === "self" ? "parent" : profile.relationship,
        }),
      }),
    onSuccess: (r) => {
      toast.success("Your HealthThread is ready");
      finish(r);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 422) setErrors(fieldErrors(e.detail));
      else toast.error(e.message);
    },
  });

  const switchTo = (w: "self" | "other") => {
    setForWhom(w);
    setProfile((p) => ({
      ...p,
      display_name: w === "self" ? name : "",
      relationship: w === "self" ? "self" : "parent",
    }));
  };

  return (
    <Card>
      <CardHeader>
        <BackButton onClick={onBack} />
        <CardTitle className="text-xl">Create your first health profile</CardTitle>
        <CardDescription>You can add more family members later.</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            setErrors({});
            submit.mutate();
          }}
        >
          <Field label="Your name" htmlFor="me_name" error={errors.name}>
            <Input id="me_name" value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">This profile is for</legend>
            <div className="grid grid-cols-2 gap-2">
              {(["self", "other"] as const).map((w) => (
                <button
                  type="button"
                  key={w}
                  onClick={() => switchTo(w)}
                  aria-pressed={forWhom === w}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-sm transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
                    forWhom === w ? "border-primary bg-accent font-medium" : "bg-card hover:bg-muted",
                  )}
                >
                  {w === "self" ? "Myself" : "Someone I care for"}
                </button>
              ))}
            </div>
          </fieldset>
          <ProfileFields value={profile} onChange={setProfile} errors={errors} forSomeoneElse={forWhom === "other"} />
          <Button type="submit" size="lg" className="w-full" disabled={submit.isPending}>
            {submit.isPending && <Loader2 className="animate-spin" />} Create profile
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function DoctorForm({ me, onBack }: { me: Me; onBack: () => void }) {
  const { data: config } = useAuthConfig();
  const [form, setForm] = useState({
    full_name: me.name.startsWith("Dr") ? me.name : `Dr. ${me.name}`,
    specialty: "",
    organization: "",
    council: "",
    registration_number: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const finish = useFinish();
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = useMutation({
    mutationFn: () => api.post<LoginResult>("/onboarding/doctor", form),
    onSuccess: (r) => {
      toast.success("Submitted for verification");
      finish(r);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 422) setErrors(fieldErrors(e.detail));
      else toast.error(e.message);
    },
  });

  return (
    <Card>
      <CardHeader>
        <BackButton onClick={onBack} />
        <CardTitle className="text-xl">Your professional details</CardTitle>
        <CardDescription>
          We check your registration against the medical register before you can see any patient record. Signing in with
          your hospital email speeds this up.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            setErrors({});
            submit.mutate();
          }}
        >
          <Field label="Full name" htmlFor="full_name" error={errors.full_name} className="sm:col-span-2">
            <Input id="full_name" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} required />
          </Field>
          <Field label="Specialty" htmlFor="specialty" error={errors.specialty}>
            <NativeSelect id="specialty" value={form.specialty} onChange={(e) => set("specialty", e.target.value)} required>
              <option value="" disabled>
                Choose…
              </option>
              {config?.specialties.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Hospital / clinic" htmlFor="organization" error={errors.organization}>
            <Input id="organization" value={form.organization} onChange={(e) => set("organization", e.target.value)} required />
          </Field>
          <Field label="Medical council" htmlFor="council" error={errors.council} hint="Start typing, e.g. Tamil Nadu Medical Council">
            <Input id="council" list="council-list" value={form.council} onChange={(e) => set("council", e.target.value)} required />
          </Field>
          <CouncilList councils={config?.councils ?? []} />
          <Field label="Registration number" htmlFor="registration_number" error={errors.registration_number} hint="e.g. TNMC-58213">
            <Input
              id="registration_number"
              value={form.registration_number}
              onChange={(e) => set("registration_number", e.target.value)}
              required
            />
          </Field>
          <Button type="submit" size="lg" className="sm:col-span-2" disabled={submit.isPending}>
            {submit.isPending && <Loader2 className="animate-spin" />} Submit for verification
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="mb-1 inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" /> Back
    </button>
  );
}
