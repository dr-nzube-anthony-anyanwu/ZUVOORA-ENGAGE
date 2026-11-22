"use client";

import { useActionState, type ReactNode } from "react";
import type { ActionState } from "@/lib/types";

type Props = {
  action: (state: ActionState, form: FormData) => Promise<ActionState>;
  submitLabel: string;
  children?: ReactNode;
  className?: string;
  /** Visual style of the submit button. */
  tone?: "primary" | "secondary" | "danger";
  /** Ask for confirmation before submitting (for destructive actions). */
  confirmText?: string;
};

/** A form bound to a Server Action, with pending state and the action's result message. */
export function ActionForm({
  action, submitLabel, children, className, tone = "primary", confirmText,
}: Props) {
  const [state, formAction, pending] = useActionState(action, null);
  return (
    <form
      action={formAction}
      className={className ?? "form"}
      onSubmit={(event) => {
        if (confirmText && !window.confirm(confirmText)) event.preventDefault();
      }}
    >
      {children}
      <div className="form-actions">
        <button type="submit" disabled={pending} className={tone === "primary" ? undefined : tone}>
          {pending ? "Working…" : submitLabel}
        </button>
        {state?.ok && !pending && <span role="status" className="ok">{state.ok}</span>}
      </div>
      {state?.ok && !pending && state.details && state.details.length > 0 && (
        <ul className="ok-details mono">{state.details.map((d) => <li key={d}>{d}</li>)}</ul>
      )}
      {state?.error && !pending && (
        <div role="alert" className="error">
          {state.error}
          {state.details && state.details.length > 0 && (
            <ul>{state.details.map((d) => <li key={d}>{d}</li>)}</ul>
          )}
        </div>
      )}
    </form>
  );
}

/** A one-button form for actions without fields (publish, archive, verify…). */
export function ActionButton(props: Omit<Props, "children" | "className">) {
  return <ActionForm {...props} className="inline-form" />;
}
