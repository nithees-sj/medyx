"use client";

import { useState } from "react";

import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";

export interface ProfileFormValue {
  display_name: string;
  relationship: "self" | "parent" | "child" | "spouse" | "other";
  dob: string;
  sex: "male" | "female" | "other" | "unknown";
  blood_group: string;
  emergency_contact_name: string;
  emergency_contact_phone: string;
}

export const emptyProfile: ProfileFormValue = {
  display_name: "",
  relationship: "self",
  dob: "",
  sex: "unknown",
  blood_group: "unknown",
  emergency_contact_name: "",
  emergency_contact_phone: "",
};

const BLOOD = ["unknown", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"];

/** Shared by onboarding and "add a family member". */
export function ProfileFields({
  value,
  onChange,
  errors = {},
  forSomeoneElse,
}: {
  value: ProfileFormValue;
  onChange: (v: ProfileFormValue) => void;
  errors?: Partial<Record<keyof ProfileFormValue, string>>;
  forSomeoneElse: boolean;
}) {
  const set = <K extends keyof ProfileFormValue>(k: K, v: ProfileFormValue[K]) => onChange({ ...value, [k]: v });
  const [today] = useState(() => new Date().toISOString().slice(0, 10));
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label={forSomeoneElse ? "Their full name" : "Your full name"} htmlFor="display_name" error={errors.display_name} className="sm:col-span-2">
        <Input id="display_name" value={value.display_name} onChange={(e) => set("display_name", e.target.value)} autoComplete="off" required />
      </Field>
      {forSomeoneElse && (
        <Field label="They are my…" htmlFor="relationship" error={errors.relationship}>
          <NativeSelect id="relationship" value={value.relationship} onChange={(e) => set("relationship", e.target.value as ProfileFormValue["relationship"])}>
            <option value="parent">Parent</option>
            <option value="child">Child</option>
            <option value="spouse">Spouse</option>
            <option value="other">Other family member</option>
          </NativeSelect>
        </Field>
      )}
      <Field label="Date of birth" htmlFor="dob" error={errors.dob}>
        <Input id="dob" type="date" max={today} value={value.dob} onChange={(e) => set("dob", e.target.value)} required />
      </Field>
      <Field label="Sex" htmlFor="sex" error={errors.sex}>
        <NativeSelect id="sex" value={value.sex} onChange={(e) => set("sex", e.target.value as ProfileFormValue["sex"])}>
          <option value="unknown">Prefer not to say</option>
          <option value="female">Female</option>
          <option value="male">Male</option>
          <option value="other">Other</option>
        </NativeSelect>
      </Field>
      <Field label="Blood group" htmlFor="blood_group" error={errors.blood_group}>
        <NativeSelect id="blood_group" value={value.blood_group} onChange={(e) => set("blood_group", e.target.value)}>
          {BLOOD.map((b) => (
            <option key={b} value={b}>
              {b === "unknown" ? "Not sure" : b}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <Field label="Emergency contact name" htmlFor="ec_name" error={errors.emergency_contact_name}>
        <Input id="ec_name" value={value.emergency_contact_name} onChange={(e) => set("emergency_contact_name", e.target.value)} />
      </Field>
      <Field label="Emergency contact phone" htmlFor="ec_phone" error={errors.emergency_contact_phone}>
        <Input id="ec_phone" type="tel" inputMode="tel" placeholder="+91 98400 12345" value={value.emergency_contact_phone} onChange={(e) => set("emergency_contact_phone", e.target.value)} />
      </Field>
    </div>
  );
}

/** Turn FastAPI 422 details into per-field messages. */
export function fieldErrors(detail: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  if (Array.isArray(detail)) {
    for (const d of detail as { loc?: (string | number)[]; msg?: string }[]) {
      const key = String(d.loc?.[d.loc.length - 1] ?? "");
      if (key && d.msg) out[key] = d.msg.replace(/^Value error, /, "");
    }
  }
  return out;
}

export function toProfilePayload(v: ProfileFormValue) {
  return {
    ...v,
    emergency_contact_name: v.emergency_contact_name || null,
    emergency_contact_phone: v.emergency_contact_phone || null,
  };
}
