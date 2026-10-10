import { cn } from "@/lib/utils";

/** HealthThread wordmark: a thread weaving through three record "beads". */
export function Logo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight", className)}>
      <svg viewBox="0 0 32 32" aria-hidden className="size-7 shrink-0">
        <rect width="32" height="32" rx="8" className="fill-primary" />
        <path
          d="M5 20c4-8 7-8 11 0s7 8 11 0"
          fill="none"
          stroke="white"
          strokeWidth="2.4"
          strokeLinecap="round"
        />
        <circle cx="9" cy="15.5" r="2.4" fill="white" />
        <circle cx="16" cy="20" r="2.4" fill="white" />
        <circle cx="23" cy="15.5" r="2.4" fill="white" />
      </svg>
      {!compact && <span className="text-lg">HealthThread</span>}
    </span>
  );
}
