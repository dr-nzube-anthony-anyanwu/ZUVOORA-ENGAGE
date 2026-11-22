"use client";

import { useActionState, useId } from "react";
import { submitDemoRequest, type DemoRequestState } from "@/lib/public-actions";

const INTERESTS = [
  { value: "demo", label: "A demo of ZUVOORA Engage" },
  { value: "pilot", label: "Joining the pilot programme" },
  { value: "pricing", label: "Plans and pricing" },
  { value: "accessibility", label: "Accessibility feedback" },
  { value: "other", label: "Something else" },
];

function Input({ label, name, type = "text", required, autoComplete, maxLength, hint }: {
  label: string; name: string; type?: string; required?: boolean; autoComplete?: string;
  maxLength: number; hint?: string;
}) {
  const id = useId();
  return (
    <div className="mk-field">
      <label htmlFor={id}>{label}{required ? <span aria-hidden="true"> *</span> : <span className="mk-optional"> (optional)</span>}</label>
      <input id={id} name={name} type={type} required={required} autoComplete={autoComplete}
             maxLength={maxLength} aria-describedby={hint ? `${id}-hint` : undefined} />
      {hint && <span id={`${id}-hint`} className="mk-field-hint">{hint}</span>}
    </div>
  );
}

/** Demo / pilot request form. Asks only for business contact details — never health information. */
export function DemoRequestForm({ interest = "demo" }: { interest?: string }) {
  const [state, action, pending] = useActionState<DemoRequestState, FormData>(submitDemoRequest, null);
  const messageId = useId();
  const interestId = useId();

  if (state?.ok) {
    return (
      <div className="mk-form-success" role="status">
        <h2>Thank you — we&apos;ve received your request.</h2>
        <p>Someone from ZubeVision will contact you by email to arrange a time. You don&apos;t need to do anything else.</p>
      </div>
    );
  }

  return (
    <form action={action} className="mk-form" noValidate={false}>
      <p className="mk-form-note">Fields marked * are required. Please don&apos;t include any patient or health information.</p>
      <div className="mk-form-grid">
        <Input label="Your name" name="name" required autoComplete="name" maxLength={120} />
        <Input label="Your role" name="role" autoComplete="organization-title" maxLength={80} />
        <Input label="Clinic or organisation" name="clinic_name" required autoComplete="organization" maxLength={160} />
        <Input label="Work email" name="email" type="email" required autoComplete="email" maxLength={254} />
        <Input label="Phone" name="phone" type="tel" autoComplete="tel" maxLength={30} />
        <Input label="City" name="city" autoComplete="address-level2" maxLength={80} />
        <Input label="Country" name="country" autoComplete="country-name" maxLength={80} />
        <div className="mk-field">
          <label htmlFor={interestId}>Interested in</label>
          <select id={interestId} name="interest" defaultValue={INTERESTS.some((i) => i.value === interest) ? interest : "demo"}>
            {INTERESTS.map((i) => <option key={i.value} value={i.value}>{i.label}</option>)}
          </select>
        </div>
      </div>
      <div className="mk-field">
        <label htmlFor={messageId}>Anything we should know? <span className="mk-optional">(optional)</span></label>
        <textarea id={messageId} name="message" rows={4} maxLength={1000}
                  placeholder="For example: your website, number of branches, or what you'd like to see." />
      </div>
      {/* Honeypot: hidden from people and assistive technology; bots that fill it are ignored. */}
      <div className="mk-hp" aria-hidden="true">
        <label>Website <input name="website" tabIndex={-1} autoComplete="off" /></label>
      </div>
      <label className="mk-consent">
        <input type="checkbox" name="consent" required />
        <span>I agree that ZubeVision Technologies Ltd. may contact me about this request. We use these details only to respond and keep them for up to 12 months.</span>
      </label>
      {state?.error && (
        <div role="alert" className="mk-form-error">
          {state.error}
          {state.details && state.details.length > 0 && <ul>{state.details.map((d) => <li key={d}>{d}</li>)}</ul>}
        </div>
      )}
      <button type="submit" className="mk-btn mk-btn-primary mk-btn-lg" disabled={pending}>
        {pending ? "Sending…" : "Send request"}
      </button>
    </form>
  );
}
