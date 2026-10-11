import { AlertOctagon, AlertTriangle, FileStack, MessageSquareQuote, QrCode, ShieldCheck, Upload, Workflow } from "lucide-react";
import Link from "next/link";

import { Logo } from "@/components/brand/logo";
import { LandingCta } from "@/components/landing-cta";
import { SystemStatus } from "@/components/system-status";

const ORGS = [
  { name: "Sunrise Diabetes Hospital", color: "#2563eb", doc: "OPD note · Mar 2024" },
  { name: "Lakeview Heart Institute", color: "#db2777", doc: "Cardiology · Jan 2025" },
  { name: "Anand Family Clinic", color: "#0891b2", doc: "Handwritten Rx · Apr 2025" },
  { name: "City Diagnostics", color: "#4a3aa7", doc: "Lab report · Jan 2026" },
  { name: "Medline Path Labs", color: "#c026d3", doc: "Lab report (SI units) · Aug 2026" },
];

const ENGINES = [
  {
    icon: Upload,
    title: "Smart Ingest",
    body: "PDFs, phone photos and handwritten prescriptions become coded FHIR R4 records, each fact linked to its page.",
  },
  {
    icon: ShieldCheck,
    title: "Cross-hospital safety",
    body: "Deterministic rules catch duplicate medicines, allergy conflicts, side-effect cascades and silent lab drift.",
  },
  {
    icon: MessageSquareQuote,
    title: "Clinical copilot",
    body: "Doctors ask the record in plain language. Every answer cites the document it came from.",
  },
  {
    icon: QrCode,
    title: "Consent vault",
    body: "Patients share by QR, choose what and for how long, see every access, and revoke instantly.",
  },
];

export default function Home() {
  return (
    <main className="flex-1">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 py-5">
        <Logo />
        <Link href="/login" className="text-sm font-medium text-primary hover:underline">
          Sign in
        </Link>
      </header>

      <section className="mx-auto grid w-full max-w-6xl items-center gap-10 px-4 pt-6 pb-16 lg:grid-cols-[1.1fr_1fr]">
        <div className="space-y-6">
          <h1 className="text-4xl leading-tight font-semibold tracking-tight sm:text-5xl">
            One patient, one record, every hospital.
          </h1>
          <p className="max-w-xl text-lg text-muted-foreground">
            HealthThread turns scattered prescriptions, lab reports and discharge summaries into a single FHIR record, and catches
            what no single hospital can see.
          </p>
          <LandingCta />
          <SystemStatus />
        </div>

        <div className="relative rounded-2xl border bg-card p-5 shadow-sm" aria-hidden>
          <p className="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Rajan&apos;s records, 5 sources</p>
          <ul className="space-y-2">
            {ORGS.map((o) => (
              <li key={o.name} className="flex items-center gap-3 rounded-lg border px-3 py-2 text-sm" style={{ borderLeft: `4px solid ${o.color}` }}>
                <FileStack className="size-4 shrink-0" style={{ color: o.color }} />
                <span className="min-w-0 flex-1 truncate font-medium">{o.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{o.doc}</span>
              </li>
            ))}
          </ul>
          <div className="my-4 flex items-center gap-2 text-xs text-muted-foreground">
            <Workflow className="size-4 text-primary" /> merged into one coded record
          </div>
          <div className="space-y-2">
            <p className="flex items-center gap-2 rounded-lg bg-critical-soft px-3 py-2 text-sm">
              <AlertOctagon className="size-4 shrink-0 text-critical" />
              <span>
                <b>Critical:</b> penicillin allergy vs Novamox (amoxicillin)
              </span>
            </p>
            <p className="flex items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm">
              <AlertTriangle className="size-4 shrink-0 text-warning" />
              <span>Metformin twice: Glycomet + Glucophage</span>
            </p>
            <p className="flex items-center gap-2 rounded-lg bg-warning-soft px-3 py-2 text-sm">
              <AlertTriangle className="size-4 shrink-0 text-warning" />
              <span>eGFR 72 → 61 → 52 → 47 across 4 labs, on metformin</span>
            </p>
          </div>
        </div>
      </section>

      <section className="border-y bg-card/60">
        <div className="mx-auto w-full max-w-6xl px-4 py-14">
          <h2 className="text-2xl font-semibold tracking-tight">How it works</h2>
          <ol className="mt-6 grid gap-6 sm:grid-cols-3">
            {[
              ["Upload anything", "Snap the prescription on the fridge, forward the PDF from WhatsApp. Any hospital, any format."],
              ["One merged record", "Same test, different names and units → one series. Brands → generics. Every fact keeps a link to its page."],
              ["Share safely", "Show the doctor a QR code. They see only what you choose, for as long as you choose, and every view is logged."],
            ].map(([t, b], i) => (
              <li key={t} className="space-y-2">
                <span className="flex size-8 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                  {i + 1}
                </span>
                <p className="font-medium">{t}</p>
                <p className="text-sm text-muted-foreground">{b}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="mx-auto w-full max-w-6xl px-4 py-14">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {ENGINES.map((e) => (
            <div key={e.title} className="rounded-xl border bg-card p-5">
              <e.icon className="size-6 text-primary" />
              <p className="mt-3 font-medium">{e.title}</p>
              <p className="mt-1 text-sm text-muted-foreground">{e.body}</p>
            </div>
          ))}
        </div>
        <p className="mt-8 text-center text-xs text-muted-foreground">
          Built on FHIR R4 (HAPI FHIR), LOINC and UCUM. Alerts and copilot answers are decision support for clinicians — never orders.
        </p>
      </section>
    </main>
  );
}
