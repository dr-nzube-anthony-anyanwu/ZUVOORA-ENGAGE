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
  ".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.webp,application/pdf,text/plain,text/markdown," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  "image/png,image/jpeg,image/webp";

export const FILE_HINT =
  "PDF, Word (.docx), text, Markdown, or a photo (.jpg, .png, .webp) of a price list, flyer or " +
  "sign. Up to 10 MB. Photos and scanned PDFs (up to 10 pages) are read by AI — never upload " +
  "anything containing patient information.";

export const AI_READ_NOTICE =
  "Read by AI from an image. AI can misread numbers and names — compare every line with the " +
  "original before approving.";
