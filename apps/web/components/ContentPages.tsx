/** Shared list and edit pages for branches, services and FAQs. */
import Link from "next/link";
import { ActionButton, ActionForm } from "@/components/ActionForm";
import { ContentFields, KIND_TEXT, contentTitle, type ContentKind } from "@/components/ContentFields";
import { ReadOnlyNotice, StateBadge, formatDate } from "@/components/ui";
import { contentAction, createContent, saveContent } from "@/lib/actions";
import { load, loadClinic, loadWithQuery, requireIds } from "@/lib/clinic";
import { canEdit, type ContentItem, type OpeningHours } from "@/lib/types";

const LABELS: Record<string, string> = {
  name: "Name", city: "City", address: "Address", phone: "Phone", email: "Email",
  timezone: "Time zone", notes: "Notes", opening_hours: "Opening hours", category: "Category",
  description: "Description", duration_minutes: "Duration (minutes)", price_note: "Price",
  question: "Question", answer: "Answer", sort_order: "Display order",
};

function hoursText(value: OpeningHours): string {
  const days = value.weekly.map((d) =>
    `${d.day.toUpperCase()}: ${d.closed ? "closed" : d.ranges.map((r) => `${r.open}–${r.close}`).join(", ")}`);
  const special = value.exceptions.map((e) =>
    `${e.date}: ${e.closed ? "closed" : e.ranges.map((r) => `${r.open}–${r.close}`).join(", ")}${e.note ? ` (${e.note})` : ""}`);
  return [...days, ...special].join("\n");
}

/** Readable, text-only rendering of a published item. */
function ContentSummary({ value }: { value: unknown }) {
  const entries = Object.entries(value as Record<string, unknown>).filter(([, v]) => v !== null);
  return (
    <dl className="details">
      {entries.map(([key, v]) => (
        <div key={key}>
          <dt>{LABELS[key] ?? key}</dt>
          <dd className="pre-line">{key === "opening_hours" ? hoursText(v as OpeningHours) : String(v)}</dd>
        </div>
      ))}
    </dl>
  );
}

export async function ContentListPage({ tenantId, kind, showArchived }: {
  tenantId: string; kind: ContentKind; showArchived: boolean;
}) {
  const clinic = await loadClinic(tenantId);
  const items = await loadWithQuery<ContentItem<unknown>[]>(
    tenantId, [kind], showArchived ? { include_archived: "true" } : {},
  );
  const text = KIND_TEXT[kind];
  const editable = canEdit(clinic.my_role);
  const base = `/clinics/${tenantId}/${kind}`;

  return (
    <>
      <h1>{text.title}</h1>
      <p>{text.intro}</p>
      <section className="panel">
        {items.length === 0 ? (
          <p>No {text.singular} yet.</p>
        ) : (
          <table className="table">
            <thead><tr><th scope="col">Name</th><th scope="col">Status</th><th scope="col">Updated</th></tr></thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td><Link href={`${base}/${item.id}`}>{contentTitle(kind, item.draft)}</Link></td>
                  <td><StateBadge state={item.state} /></td>
                  <td className="muted">{formatDate(item.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="hint">
          {showArchived
            ? <Link href={base}>Hide archived</Link>
            : <Link href={`${base}?archived=1`}>Show archived</Link>}
        </p>
      </section>
      {editable ? (
        <section className="panel">
          <h2>Add a {text.singular}</h2>
          <ActionForm action={createContent.bind(null, kind, tenantId)} submitLabel="Create draft">
            <ContentFields kind={kind} />
          </ActionForm>
        </section>
      ) : <ReadOnlyNotice />}
    </>
  );
}

export async function ContentItemPage({ tenantId, kind, itemId }: {
  tenantId: string; kind: ContentKind; itemId: string;
}) {
  requireIds(itemId);
  const clinic = await loadClinic(tenantId);
  const item = await load<ContentItem<unknown>>(tenantId, kind, itemId);
  const text = KIND_TEXT[kind];
  const editable = canEdit(clinic.my_role);
  const archived = item.state === "archived";
  const act = (verb: string) => contentAction.bind(null, kind, tenantId, item.id, verb, item.revision);

  return (
    <>
      <p><Link href={`/clinics/${tenantId}/${kind}`}>← {text.title}</Link></p>
      <h1>{contentTitle(kind, item.draft)}</h1>
      <section className="panel">
        <div className="row-between">
          <StateBadge state={item.state} />
          <span className="hint">
            Revision {item.revision} · last published {formatDate(item.published_at)}
          </span>
        </div>
        {!editable && <ReadOnlyNotice />}
        {archived && <p className="notice-inline">Archived items are hidden from patients. Restore to edit.</p>}
        <ActionForm action={saveContent.bind(null, kind, tenantId, item.id, item.revision)}
                    submitLabel="Save draft">
          <fieldset disabled={!editable || archived}>
            <ContentFields kind={kind} value={item.draft} />
          </fieldset>
        </ActionForm>
        {editable && (
          <div className="actions-row">
            {!archived && item.state !== "published" && (
              <ActionButton action={act("publish")} submitLabel={`Publish revision ${item.revision}`} />
            )}
            {item.published !== null && (
              <ActionButton action={act("unpublish")} submitLabel="Unpublish" tone="secondary"
                            confirmText={`Remove this ${text.singular} from what patients can see?`} />
            )}
            {archived
              ? <ActionButton action={act("restore")} submitLabel="Restore" tone="secondary" />
              : <ActionButton action={act("archive")} submitLabel="Archive" tone="danger"
                              confirmText={`Archive this ${text.singular}? It will be unpublished.`} />}
          </div>
        )}
      </section>
      {item.state === "changes_pending" && item.published !== null && (
        <section className="panel">
          <h2>Currently live (revision {item.published_revision})</h2>
          <p className="hint">Patients see this version until you publish the draft above.</p>
          <ContentSummary value={item.published} />
        </section>
      )}
    </>
  );
}
