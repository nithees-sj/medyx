export interface SourceRef {
  document_id: string;
  doc_label: string;
  page: number;
  snippet: string | null;
  org: string | null;
  document_date: string | null;
  filename: string;
}

export type OrgColors = Record<string, string>;

export interface TimelineItem {
  id: string;
  group: "conditions" | "medications" | "labs" | "documents";
  kind: "point" | "range";
  title: string;
  subtitle: string | null;
  start: string;
  end?: string;
  ongoing?: boolean;
  org: string | null;
  status: string | null;
  document_id?: string;
  sources: SourceRef[];
}

export interface TimelineData {
  groups: { id: string; label: string }[];
  items: TimelineItem[];
  org_colors: OrgColors;
}

export interface ObservationPoint {
  ref: string;
  loinc: string | null;
  name: string;
  value: number | null;
  value_text: string;
  unit: string | null;
  unit_display: string;
  date: string | null;
  interpretation: string | null;
  ref_low: number | null;
  ref_high: number | null;
  org: string | null;
  written_text: string | null;
  sources: SourceRef[];
}

export interface DriftInfo {
  slope_per_year: number;
  intercept_date: string;
  fitted: { date: string; value: number }[];
  projection: { date: string; value: number }[];
  threshold: number;
  threshold_label: string;
  projected_cross_date: string | null;
  alert_id: string | null;
}

export interface Analyte {
  loinc: string;
  name: string;
  display: string;
  unit: string;
  decimals: number;
  ref_low: number | null;
  ref_high: number | null;
  count: number;
  points: ObservationPoint[];
  latest: ObservationPoint;
  drift: DriftInfo | null;
}

export interface MedicationRow {
  ref: string;
  generic: string;
  display: string;
  brand: string | null;
  classes: string[];
  strength: string | null;
  frequency_label: string;
  frequency_text: string | null;
  as_needed: boolean;
  instructions: string | null;
  start: string | null;
  end: string | null;
  status: "active" | "completed" | "stopped";
  org: string | null;
  requester: string | null;
  written_text: string | null;
  sources: SourceRef[];
}

export interface DocumentRow {
  id: string;
  label: string;
  seq: number;
  original_filename: string;
  mime: string;
  page_count: number;
  status: "queued" | "processing" | "needs_review" | "done" | "failed";
  stage: string;
  error: string | null;
  document_type: string | null;
  document_date: string | null;
  source_org_name: string | null;
  result_counts: Record<string, number> | null;
  uploader_role: string;
  created_at: string;
  updated_at: string;
}

export interface UploadResult {
  filename: string;
  document: DocumentRow | null;
  duplicate: boolean;
  error: string | null;
}

export interface ReviewItem {
  id: string;
  document_id: string;
  document_label: string;
  document_filename: string;
  document_mime: string;
  document_date: string | null;
  source_org_name: string | null;
  resource_type: "Condition" | "MedicationRequest" | "AllergyIntolerance" | "Observation" | "Vital";
  raw: Record<string, unknown>;
  normalized: Record<string, unknown>;
  editable: string[];
  confidence: number;
  page: number;
  snippet: string | null;
  uncertain_reason: string | null;
  created_at: string;
}
