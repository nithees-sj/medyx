import { Logo } from "@/components/brand/logo";
import { SystemStatus } from "@/components/system-status";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-start justify-center gap-6 px-4 py-16">
      <Logo />
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
        One patient, one record, every hospital.
      </h1>
      <p className="max-w-xl text-muted-foreground">
        HealthThread turns scattered prescriptions, lab reports and discharge summaries into a
        single FHIR record, and catches what no single hospital can see.
      </p>
      <SystemStatus />
    </main>
  );
}
