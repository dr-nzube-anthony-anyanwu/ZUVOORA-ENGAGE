import Link from "next/link";
import { Badge, formatDate } from "@/components/ui";
import { loadClinic, loadWithQuery } from "@/lib/clinic";
import { CONVERSATION_STATE, HANDOVER_STATE, VIEWS, inboxView } from "@/lib/inbox";
import { canHandleInbox, type ConversationSummary, type Handover } from "@/lib/types";

export default async function InboxPage({ params, searchParams }: {
  params: Promise<{ tenantId: string }>;
  searchParams: Promise<{ view?: string }>;
}) {
  const [{ tenantId }, { view: rawView }] = await Promise.all([params, searchParams]);
  const clinic = await loadClinic(tenantId);
  const base = `/clinics/${tenantId}/inbox`;

  if (!canHandleInbox(clinic.my_role)) {
    return (
      <>
        <h1>Inbox</h1>
        <p className="notice-inline">
          Patient conversations and contact details are only available to owners, admins and
          receptionists.
        </p>
      </>
    );
  }

  const view = inboxView(rawView);
  return (
    <>
      <h1>Inbox</h1>
      <p>
        Visitors who ask the assistant for the clinic team appear here with the contact details
        they agreed to share. Call them back, then mark the request as resolved.
      </p>
      <nav className="tabs" aria-label="Inbox views">
        {VIEWS.map((v) => (
          <Link key={v.key} href={`${base}?view=${v.key}`}
            aria-current={v.key === view ? "page" : undefined}>
            {v.label}
          </Link>
        ))}
      </nav>
      <section className="panel">
        {view === "conversations"
          ? <Conversations tenantId={tenantId} base={base} />
          : <Handovers tenantId={tenantId} base={base} view={view} />}
      </section>
    </>
  );
}

async function Handovers({ tenantId, base, view }: {
  tenantId: string; base: string; view: "open" | "resolved";
}) {
  const handovers = await loadWithQuery<Handover[]>(tenantId, ["handovers"], { view });
  if (handovers.length === 0) {
    return <p>{view === "open" ? "No one is waiting for a call back." : "No resolved requests yet."}</p>;
  }
  return (
    <table className="table">
      <thead>
        <tr><th scope="col">Visitor</th><th scope="col">Contact</th><th scope="col">Status</th>
          <th scope="col">Asked</th></tr>
      </thead>
      <tbody>
        {handovers.map((h) => (
          <tr key={h.id}>
            <td>
              <Link prefetch={false} href={`${base}/${h.conversation_id}`}>{h.contact_name ?? "Visitor (no name given)"}</Link>
            </td>
            <td>
              {h.contact_phone && <div>{h.contact_phone}</div>}
              {h.contact_email && <div>{h.contact_email}</div>}
            </td>
            <td><Badge tone={HANDOVER_STATE[h.status].tone}>{HANDOVER_STATE[h.status].label}</Badge></td>
            <td className="muted">{formatDate(h.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

async function Conversations({ tenantId, base }: { tenantId: string; base: string }) {
  const conversations = await loadWithQuery<ConversationSummary[]>(tenantId, ["conversations"], {});
  if (conversations.length === 0) return <p>No conversations yet.</p>;
  return (
    <table className="table">
      <thead>
        <tr><th scope="col">First question</th><th scope="col">Status</th>
          <th scope="col">Messages</th><th scope="col">Last activity</th></tr>
      </thead>
      <tbody>
        {conversations.map((c) => (
          <tr key={c.id}>
            <td><Link prefetch={false} href={`${base}/${c.id}`}>{c.preview ?? "(no question yet)"}</Link></td>
            <td>
              <Badge tone={CONVERSATION_STATE[c.status].tone}>{CONVERSATION_STATE[c.status].label}</Badge>
              {c.handover_status && (
                <> <Badge tone={HANDOVER_STATE[c.handover_status].tone}>
                  {HANDOVER_STATE[c.handover_status].label}
                </Badge></>
              )}
            </td>
            <td>{c.message_count}</td>
            <td className="muted">{formatDate(c.last_message_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
