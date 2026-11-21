import type { KnowledgeDocument, KnowledgeVersion } from "@/lib/types";

export const DOC_STATE: Record<KnowledgeDocument["state"], { label: string; tone: string }> = {
  awaiting_review: { label: "Awaiting review", tone: "warn" },
  published: { label: "Live", tone: "good" },
  changes_pending: { label: "Live · new version to review", tone: "warn" },
  unpublished: { label: "Not live", tone: "neutral" },
  archived: { label: "Archived", tone: "neutral" },
};

export const VERSION_STATE: Record<KnowledgeVersion["status"], { label: string; tone: string }> = {
  extracted: { label: "Awaiting review", tone: "warn" },
  approved: { label: "Approved", tone: "good" },
  rejected: { label: "Rejected", tone: "bad" },
  failed: { label: "Failed", tone: "bad" },
};

/** File picker filter (convenience only — the API checks the real file contents). */
export const ACCEPT =
  ".pdf,.docx,.txt,.md,application/pdf,text/plain,text/markdown," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
