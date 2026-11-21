/** Small presentational helpers shared by dashboard pages (server components). */
import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from "react";
import type { ContentState } from "@/lib/types";

const STATE: Record<ContentState, { label: string; tone: string }> = {
  draft: { label: "Draft – not live", tone: "neutral" },
  published: { label: "Live", tone: "good" },
  changes_pending: { label: "Live · unpublished changes", tone: "warn" },
  archived: { label: "Archived", tone: "neutral" },
};

export function StateBadge({ state }: { state: ContentState }) {
  const { label, tone } = STATE[state];
  return <span className={`badge ${tone}`}>{label}</span>;
}

export function Badge({ tone = "neutral", children }: { tone?: string; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

type ControlProps = { id?: string; "aria-describedby"?: string };

/**
 * A labelled form control. The label names the control; the hint is linked with
 * aria-describedby so assistive technology reads it as a description, not as the name.
 */
export function Field({
  label, hint, children,
}: { label: string; hint?: string; children: ReactElement<ControlProps> }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const control = isValidElement(children)
    ? cloneElement(children, { id, "aria-describedby": hint ? hintId : undefined })
    : children;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {control}
      {hint && <span id={hintId} className="hint">{hint}</span>}
    </div>
  );
}

export function ReadOnlyNotice() {
  return (
    <p className="notice-inline">
      You have read-only access. Owners and admins can edit and publish.
    </p>
  );
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short" })
    .format(new Date(value));
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}
