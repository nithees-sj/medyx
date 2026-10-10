import { AlertOctagon, Phone, Pill, Stethoscope } from "lucide-react";

export interface EmergencyData {
  name: string;
  age: number;
  sex: string;
  blood_group: string;
  allergies: { substance: string; reaction: string | null; criticality: string | null }[];
  medications: { name: string; brand: string | null; frequency: string }[];
  conditions: string[];
  emergency_contact: { name: string | null; phone: string | null } | null;
  healththread_id: string;
  last_updated?: string;
}

/** What a responder sees. Shared by the public page and the owner's preview. */
export function EmergencyCardView({ data }: { data: EmergencyData }) {
  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-2xl font-semibold tracking-tight">{data.name}</p>
          <p className="text-muted-foreground">
            {data.age} yrs · {data.sex}
          </p>
        </div>
        <div className="rounded-xl border-2 border-critical px-3 py-1 text-center">
          <p className="text-[10px] font-semibold tracking-wide text-critical uppercase">Blood group</p>
          <p className="text-2xl font-bold text-critical">{data.blood_group === "unknown" ? "?" : data.blood_group}</p>
        </div>
      </div>
      <section className="rounded-xl bg-critical p-4 text-white" aria-label="Allergies">
        <p className="flex items-center gap-2 text-sm font-semibold tracking-wide uppercase">
          <AlertOctagon className="size-5" /> Allergies
        </p>
        {data.allergies.length ? (
          <ul className="mt-2 space-y-1">
            {data.allergies.map((a) => (
              <li key={a.substance} className="text-xl font-bold">
                {a.substance}
                {a.reaction && <span className="text-base font-medium opacity-90"> — {a.reaction}</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-lg font-semibold">No known allergies recorded</p>
        )}
      </section>
      <section className="rounded-xl border bg-card p-4">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <Pill className="size-4 text-primary" /> Current medicines
        </p>
        {data.medications.length ? (
          <ul className="mt-2 space-y-1 text-sm">
            {data.medications.map((m) => (
              <li key={m.name + (m.brand ?? "")}>
                <span className="font-medium">{m.name}</span>
                {m.brand && <span className="text-muted-foreground"> ({m.brand})</span>}
                <span className="text-muted-foreground"> · {m.frequency}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">None recorded</p>
        )}
      </section>
      <section className="rounded-xl border bg-card p-4">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <Stethoscope className="size-4 text-primary" /> Conditions
        </p>
        <p className="mt-2 text-sm">{data.conditions.length ? data.conditions.join(" · ") : "None recorded"}</p>
      </section>
      {data.emergency_contact && (
        <a
          href={data.emergency_contact.phone ? `tel:${data.emergency_contact.phone.replace(/\s+/g, "")}` : undefined}
          className="flex items-center gap-3 rounded-xl border-2 border-primary bg-accent/50 p-4 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <Phone className="size-6 text-primary" />
          <span>
            <span className="block text-xs text-muted-foreground">Emergency contact — tap to call</span>
            <span className="block text-lg font-semibold">
              {data.emergency_contact.name} {data.emergency_contact.phone && `· ${data.emergency_contact.phone}`}
            </span>
          </span>
        </a>
      )}
    </div>
  );
}
