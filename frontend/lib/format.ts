import { format, formatDistanceToNow, parseISO } from "date-fns";
import { formatInTimeZone } from "date-fns-tz";

export const TIMEZONE = process.env.NEXT_PUBLIC_DEFAULT_TIMEZONE || "Asia/Kolkata";

/** Date-only values ("2024-03-12") — no timezone conversion. */
export function fmtDate(d: string | null | undefined, pattern = "d MMM yyyy"): string {
  if (!d) return "—";
  try {
    return format(parseISO(d.slice(0, 10)), pattern);
  } catch {
    return d;
  }
}

/** Instants (UTC timestamps) shown in the user's timezone. */
export function fmtInstant(ts: string | null | undefined, pattern = "d MMM yyyy, h:mm a"): string {
  if (!ts) return "—";
  return formatInTimeZone(new Date(ts), TIMEZONE, pattern);
}

export function fmtAgo(ts: string): string {
  return formatDistanceToNow(new Date(ts), { addSuffix: true });
}

export const DOC_TYPE_LABEL: Record<string, string> = {
  prescription: "Prescription",
  lab_report: "Lab report",
  discharge_summary: "Discharge summary",
  opd_note: "Consultation note",
  imaging_report: "Imaging report",
  clinical_note: "Clinical note",
  other: "Document",
};

export function docTypeLabel(t: string | null | undefined): string {
  return DOC_TYPE_LABEL[t ?? "other"] ?? "Document";
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** "3 conditions, 5 medicines, 12 lab values" from a document's result counts. */
export function countsSummary(c: Record<string, number> | null | undefined): string {
  if (!c) return "";
  const parts: string[] = [];
  if (c.conditions) parts.push(plural(c.conditions, "condition"));
  if (c.medications) parts.push(plural(c.medications, "medicine"));
  if (c.allergies) parts.push(plural(c.allergies, "allergy", "allergies"));
  if (c.labs) parts.push(plural(c.labs, "lab value"));
  if (c.vitals) parts.push(plural(c.vitals, "vital sign"));
  return parts.join(", ") || "Nothing clinical found";
}
