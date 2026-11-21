/** Form fields for branches, services and FAQs (server components; values are plain text). */
import { Field } from "@/components/ui";
import {
  DAYS, type BranchContent, type FaqContent, type HoursException, type ServiceContent,
} from "@/lib/types";

export type ContentKind = "branches" | "services" | "faqs";

const TIMEZONES = Intl.supportedValuesOf("timeZone");

function HoursEditor({ value }: { value: BranchContent["opening_hours"] }) {
  const exceptions: (HoursException | null)[] = [...(value?.exceptions ?? []), null, null];
  return (
    <fieldset className="hours">
      <legend>Opening hours</legend>
      <label className="check">
        <input type="checkbox" name="hours_enabled" defaultChecked={value !== null} />
        Publish opening hours for this branch
      </label>
      <p className="hint">
        Times are 24-hour, in the branch&apos;s time zone. Use a second range for a lunch break.
        Leave a day&apos;s times empty only if it is marked closed.
      </p>
      <table className="hours-table">
        <thead>
          <tr><th scope="col">Day</th><th scope="col">Closed</th><th scope="col">Opening times</th></tr>
        </thead>
        <tbody>
          {DAYS.map(({ key, label }) => {
            const day = value?.weekly.find((d) => d.day === key);
            const ranges = day?.ranges ?? (value ? [] : key === "sun" ? [] : [{ open: "08:00", close: "17:00" }]);
            return (
              <tr key={key}>
                <th scope="row">{label}</th>
                <td>
                  <input type="checkbox" name={`${key}_closed`} aria-label={`${label} closed`}
                         defaultChecked={day ? day.closed : key === "sun"} />
                </td>
                <td className="ranges">
                  {[0, 1, 2].map((i) => (
                    <span key={i} className="range">
                      <input type="time" name={`${key}_open_${i}`} aria-label={`${label} opens (${i + 1})`}
                             defaultValue={ranges[i]?.open ?? ""} />
                      –
                      <input type="time" name={`${key}_close_${i}`} aria-label={`${label} closes (${i + 1})`}
                             defaultValue={ranges[i]?.close ?? ""} />
                    </span>
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <h3>Holidays and special days</h3>
      <p className="hint">Leave the date empty to remove a row. Save to get more empty rows.</p>
      <table className="hours-table">
        <thead>
          <tr>
            <th scope="col">Date</th><th scope="col">Closed</th><th scope="col">Hours</th>
            <th scope="col">Note</th>
          </tr>
        </thead>
        <tbody>
          {exceptions.map((ex, i) => (
            <tr key={i}>
              <td>
                <input type="hidden" name="ex_index" value={i} />
                <input type="date" name={`ex_${i}_date`} aria-label={`Special day ${i + 1} date`}
                       defaultValue={ex?.date ?? ""} />
              </td>
              <td>
                <input type="checkbox" name={`ex_${i}_closed`} aria-label={`Special day ${i + 1} closed`}
                       defaultChecked={ex ? ex.closed : true} />
              </td>
              <td className="ranges">
                <span className="range">
                  <input type="time" name={`ex_${i}_open_0`} aria-label={`Special day ${i + 1} opens`}
                         defaultValue={ex?.ranges[0]?.open ?? ""} />
                  –
                  <input type="time" name={`ex_${i}_close_0`} aria-label={`Special day ${i + 1} closes`}
                         defaultValue={ex?.ranges[0]?.close ?? ""} />
                </span>
              </td>
              <td>
                <input name={`ex_${i}_note`} maxLength={120} aria-label={`Special day ${i + 1} note`}
                       defaultValue={ex?.note ?? ""} placeholder="e.g. Christmas Day" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </fieldset>
  );
}

function BranchFields({ value }: { value?: BranchContent }) {
  return (
    <>
      <div className="grid-2">
        <Field label="Branch name">
          <input name="name" required minLength={2} maxLength={120} defaultValue={value?.name ?? ""} />
        </Field>
        <Field label="City">
          <input name="city" maxLength={80} defaultValue={value?.city ?? ""} />
        </Field>
      </div>
      <Field label="Address">
        <textarea name="address" rows={2} maxLength={500} defaultValue={value?.address ?? ""} />
      </Field>
      <div className="grid-3">
        <Field label="Phone">
          <input name="phone" maxLength={30} defaultValue={value?.phone ?? ""} />
        </Field>
        <Field label="Email">
          <input name="email" type="email" maxLength={254} defaultValue={value?.email ?? ""} />
        </Field>
        <Field label="Time zone">
          <select name="timezone" defaultValue={value?.timezone ?? "Africa/Lagos"}>
            {TIMEZONES.map((tz) => <option key={tz} value={tz}>{tz}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Notes for patients" hint="Parking, accessibility, directions. Plain text.">
        <textarea name="notes" rows={2} maxLength={1000} defaultValue={value?.notes ?? ""} />
      </Field>
      {value !== undefined && <HoursEditor value={value.opening_hours} />}
    </>
  );
}

function ServiceFields({ value }: { value?: ServiceContent }) {
  return (
    <>
      <div className="grid-2">
        <Field label="Service name">
          <input name="name" required minLength={2} maxLength={120} defaultValue={value?.name ?? ""} />
        </Field>
        <Field label="Category">
          <input name="category" maxLength={60} defaultValue={value?.category ?? ""}
                 placeholder="e.g. Eye examinations" />
        </Field>
      </div>
      <Field label="Description">
        <textarea name="description" rows={3} maxLength={1500} defaultValue={value?.description ?? ""} />
      </Field>
      <div className="grid-2">
        <Field label="Typical duration (minutes)">
          <input name="duration_minutes" type="number" min={5} max={600}
                 defaultValue={value?.duration_minutes ?? ""} />
        </Field>
        <Field label="Price information" hint='Free text, e.g. "From NGN 15,000".'>
          <input name="price_note" maxLength={200} defaultValue={value?.price_note ?? ""} />
        </Field>
      </div>
    </>
  );
}

function FaqFields({ value }: { value?: FaqContent }) {
  return (
    <>
      <Field label="Question">
        <input name="question" required minLength={5} maxLength={300} defaultValue={value?.question ?? ""} />
      </Field>
      <Field label="Answer" hint="Administrative information only — no medical advice.">
        <textarea name="answer" required rows={4} maxLength={3000} defaultValue={value?.answer ?? ""} />
      </Field>
      <div className="grid-2">
        <Field label="Category">
          <input name="category" maxLength={60} defaultValue={value?.category ?? ""} />
        </Field>
        <Field label="Display order" hint="Lower numbers first.">
          <input name="sort_order" type="number" min={0} max={10000} defaultValue={value?.sort_order ?? 0} />
        </Field>
      </div>
    </>
  );
}

export function ContentFields({ kind, value }: { kind: ContentKind; value?: unknown }) {
  switch (kind) {
    case "branches": return <BranchFields value={value as BranchContent | undefined} />;
    case "services": return <ServiceFields value={value as ServiceContent | undefined} />;
    case "faqs": return <FaqFields value={value as FaqContent | undefined} />;
  }
}

export function contentTitle(kind: ContentKind, value: unknown): string {
  if (kind === "faqs") return (value as FaqContent).question;
  return (value as BranchContent | ServiceContent).name;
}

export const KIND_TEXT: Record<ContentKind, { title: string; singular: string; intro: string }> = {
  branches: {
    title: "Branches & hours",
    singular: "branch",
    intro: "Each location with its address, contacts and opening hours. Create the branch, then set its hours.",
  },
  services: {
    title: "Services",
    singular: "service",
    intro: "What the clinic offers. The assistant describes services; it never recommends treatment.",
  },
  faqs: {
    title: "FAQs",
    singular: "question",
    intro: "Common administrative questions (payments, documents to bring, walk-ins).",
  },
};
