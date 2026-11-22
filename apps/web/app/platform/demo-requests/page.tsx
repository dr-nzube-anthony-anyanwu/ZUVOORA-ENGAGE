import { ActionForm } from "@/components/ActionForm";
import { Badge, Field, formatDate } from "@/components/ui";
import { updateDemoRequest } from "@/lib/actions";
import { ApiRequestError, apiGet } from "@/lib/api";
import type { DemoRequest } from "@/lib/types";

const STATUS: Record<DemoRequest["status"], { label: string; tone: string }> = {
  new: { label: "New", tone: "warn" },
  contacted: { label: "Contacted", tone: "good" },
  closed: { label: "Closed", tone: "neutral" },
};
const INTEREST: Record<DemoRequest["interest"], string> = {
  demo: "Demo", pilot: "Pilot programme", pricing: "Pricing", accessibility: "Accessibility feedback", other: "Other",
};

/** Requests from the public website. Contact details are shown only here (MFA platform admins). */
export default async function DemoRequestsPage() {
  let requests: DemoRequest[];
  try {
    requests = await apiGet<DemoRequest[]>("/api/v1/platform/demo-requests");
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 403) {
      return <p className="notice-inline">Platform tools need an MFA-verified platform administrator.</p>;
    }
    throw error;
  }
  const waiting = requests.filter((r) => r.status === "new").length;

  return (
    <>
      <h1>Demo requests</h1>
      <p>
        Requests from the public website. {waiting} new. Requests are deleted automatically after 12
        months; contact people only about what they asked for.
      </p>
      {requests.length === 0 ? (
        <section className="panel"><p>No requests yet.</p></section>
      ) : requests.map((r) => (
        <section key={r.id} className="panel" aria-label={`Request from ${r.clinic_name}`}>
          <div className="row-between">
            <h2>{r.clinic_name}</h2>
            <Badge tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Badge>
          </div>
          <dl className="details">
            <div><dt>Interested in</dt><dd>{INTEREST[r.interest]}</dd></div>
            <div><dt>Name</dt><dd>{r.name}{r.role ? ` · ${r.role}` : ""}</dd></div>
            <div><dt>Email</dt><dd><a href={`mailto:${r.email}`}>{r.email}</a></dd></div>
            {r.phone && <div><dt>Phone</dt><dd><a href={`tel:${r.phone.replace(/[^0-9+]/g, "")}`}>{r.phone}</a></dd></div>}
            {(r.city || r.country) && <div><dt>Location</dt><dd>{[r.city, r.country].filter(Boolean).join(", ")}</dd></div>}
            {r.message && <div><dt>Message</dt><dd className="pre-line">{r.message}</dd></div>}
            <div><dt>Received</dt><dd>{formatDate(r.created_at)}</dd></div>
          </dl>
          <ActionForm action={updateDemoRequest.bind(null, r.id)} submitLabel="Save status" className="inline-form">
            <Field label="Status">
              <select name="status" defaultValue={r.status}>
                <option value="new">New</option>
                <option value="contacted">Contacted</option>
                <option value="closed">Closed</option>
              </select>
            </Field>
          </ActionForm>
        </section>
      ))}
    </>
  );
}
