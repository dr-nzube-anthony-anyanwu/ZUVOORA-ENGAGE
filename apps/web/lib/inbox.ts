/** Display labels for the conversation inbox (Phase 3e). */
import type { ConversationStatus, HandoverStatus } from "@/lib/types";

export const HANDOVER_STATE: Record<HandoverStatus, { label: string; tone: string }> = {
  new: { label: "New", tone: "bad" },
  in_progress: { label: "In progress", tone: "warn" },
  resolved: { label: "Resolved", tone: "good" },
};

export const CONVERSATION_STATE: Record<ConversationStatus, { label: string; tone: string }> = {
  open: { label: "Open", tone: "neutral" },
  handover_requested: { label: "Asked for the team", tone: "warn" },
  closed: { label: "Closed", tone: "neutral" },
};

/** How an assistant reply was produced, in words staff understand. */
export const ANSWER_SOURCE: Record<string, string> = {
  facts: "From your published information",
  emergency: "Emergency guidance",
  retrieval_ai: "AI answer from your published content",
  fallback: "Could not answer — offered the team",
  budget_exhausted: "AI limit reached — offered the team",
  handover: "Handover confirmation",
  greeting: "Greeting",
};

export const VIEWS = [
  { key: "open", label: "Needs follow-up" },
  { key: "resolved", label: "Resolved" },
  { key: "conversations", label: "All conversations" },
] as const;
export type InboxView = (typeof VIEWS)[number]["key"];

export function inboxView(value: string | undefined): InboxView {
  return VIEWS.some((v) => v.key === value) ? (value as InboxView) : "open";
}
