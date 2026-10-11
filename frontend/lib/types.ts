export type Role = "patient" | "doctor" | "admin";

export interface DoctorInfo {
  full_name: string;
  specialty: string;
  organization: string;
  council: string;
  registration_number: string;
  verification_status: "pending" | "verified" | "rejected" | "suspended";
  review_note: string | null;
  verified_at: string | null;
}

export interface Me {
  id: string;
  email: string;
  name: string;
  avatar_url: string | null;
  role: Role | null;
  onboarded: boolean;
  doctor: DoctorInfo | null;
}

export interface LoginResult {
  user: Me;
  redirect: string;
}

export interface AuthConfig {
  demo_mode: boolean;
  google_client_id: string | null;
  personas: { key: string; label: string }[];
  specialties: string[];
  councils: string[];
}

export interface Profile {
  id: string;
  display_name: string;
  relationship: "self" | "parent" | "child" | "spouse" | "other";
  dob: string;
  sex: "male" | "female" | "other" | "unknown";
  blood_group: string;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
  healththread_id: string;
  record_version: number;
  created_at: string;
  age: number;
  active_alerts: number;
  critical_alerts: number;
  documents: number;
  pending_review: number;
}

export interface NotificationItem {
  id: string;
  type: string;
  title: string;
  body: string | null;
  link: string | null;
  read_at: string | null;
  created_at: string;
}
