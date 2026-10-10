import { cn } from "@/lib/utils";

export function OrgDot({ color, className }: { color: string; className?: string }) {
  return <span className={cn("inline-block size-2.5 shrink-0 rounded-full", className)} style={{ background: color }} />;
}

export function OrgChip({ name, color, className }: { name: string | null; color: string; className?: string }) {
  if (!name) return null;
  return (
    <span
      className={cn("inline-flex max-w-full items-center gap-1.5 rounded-full border bg-card px-2 py-0.5 text-xs", className)}
      style={{ borderColor: `${color}55` }}
    >
      <OrgDot color={color} />
      <span className="truncate">{name}</span>
    </span>
  );
}

export function OrgLegend({ colors }: { colors: Record<string, string> }) {
  const entries = Object.entries(colors);
  if (!entries.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5" aria-label="Sources">
      {entries.map(([name, color]) => (
        <OrgChip key={name} name={name} color={color} />
      ))}
    </div>
  );
}
