/** Shapes returned by the Engage API (see apps/api). Display-only; the API is authoritative. */
import type { Role } from "@/lib/api";

export type TenantDetail = {
  tenant: {
    id: string;
    legal_name: string;
    display_name: string;
    status: "pending" | "active" | "suspended" | "closed";
    timezone: string;
    created_at: string;
  };
  my_role: Role;
};

export type ContentState = "draft" | "published" | "changes_pending" | "archived";

export type ContentItem<T> = {
  id: string;
  state: ContentState;
  revision: number;
  draft: T;
  published: T | null;
  published_revision: number | null;
  published_at: string | null;
  archived_at: string | null;
  updated_at: string;
};

export type ProfileContent = {
  about: string | null;
  public_phone: string | null;
  public_email: string | null;
  website_url: string | null;
  emergency_guidance: string | null;
};

export type Day = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export type TimeRange = { open: string; close: string };
export type DayHours = { day: Day; closed: boolean; ranges: TimeRange[] };
export type HoursException = {
  date: string;
  closed: boolean;
  ranges: TimeRange[];
  note: string | null;
};
export type OpeningHours = { weekly: DayHours[]; exceptions: HoursException[] };

export type BranchContent = {
  name: string;
  address: string | null;
  city: string | null;
  phone: string | null;
  email: string | null;
  timezone: string;
  opening_hours: OpeningHours | null;
  notes: string | null;
};

export type ServiceContent = {
  name: string;
  category: string | null;
  description: string | null;
  duration_minutes: number | null;
  price_note: string | null;
};

export type FaqContent = {
  question: string;
  answer: string;
  category: string | null;
  sort_order: number;
};

export type Domain = {
  id: string;
  hostname: string;
  status: "pending" | "verified" | "rejected";
  verified_at: string | null;
  last_checked_at: string | null;
  last_check_result: "verified" | "not_found" | "mismatch" | "dns_error" | "timeout" | null;
  created_at: string;
  dns_record: { type: "TXT"; name: string; value: string };
};

export type KnowledgeVersion = {
  id: string;
  version_no: number;
  status: "extracted" | "failed" | "approved" | "rejected";
  is_published: boolean;
  file_name: string;
  detected_type: "pdf" | "docx" | "text";
  size_bytes: number;
  sha256: string;
  page_count: number | null;
  text_length: number | null;
  uploaded_at: string;
  reviewed_at: string | null;
  review_note: string | null;
};

export type KnowledgeVersionDetail = KnowledgeVersion & { extracted_text: string | null };

export type KnowledgeDocument = {
  id: string;
  title: string;
  state: "awaiting_review" | "published" | "changes_pending" | "unpublished" | "archived";
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  published_version: KnowledgeVersion | null;
  latest_version: KnowledgeVersion | null;
  awaiting_review: number;
};

export type KnowledgeDocumentDetail = KnowledgeDocument & { versions: KnowledgeVersion[] };

export type Member = {
  membership_id: string;
  user_id: string;
  email: string | null;
  role: Role;
  is_active: boolean;
  created_at: string;
  revoked_at: string | null;
};

export const DAYS: { key: Day; label: string }[] = [
  { key: "mon", label: "Monday" },
  { key: "tue", label: "Tuesday" },
  { key: "wed", label: "Wednesday" },
  { key: "thu", label: "Thursday" },
  { key: "fri", label: "Friday" },
  { key: "sat", label: "Saturday" },
  { key: "sun", label: "Sunday" },
];

export const ROLE_LABEL: Record<Role, string> = {
  owner: "Owner",
  admin: "Admin",
  receptionist: "Receptionist",
  viewer: "Viewer",
};

export function canEdit(role: Role): boolean {
  return role === "owner" || role === "admin";
}

/** Result of a Server Action, shown next to the form that submitted it. */
export type ActionState = { ok?: string; error?: string; details?: string[] } | null;
