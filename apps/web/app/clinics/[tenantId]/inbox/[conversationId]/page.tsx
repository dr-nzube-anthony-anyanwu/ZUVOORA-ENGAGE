import Link from "next/link";
import { ActionButton } from "@/components/ActionForm";
import { Badge, formatDate } from "@/components/ui";
import { closeConversation, setHandoverStatus } from "@/lib/actions";
import { load, loadClinic, requireIds } from "@/lib/clinic";
import { ANSWER_SOURCE, CONVERSATION_STATE, HANDOVER_STATE } from "@/lib/inbox";
import { canHandleInbox, type ConversationDetail, type HandoverStatus } from "@/lib/types";

const NEXT_STEPS: Record<HandoverStatus, { status: HandoverStatus; label: string; tone: "primary" | "secondary" }[]> = {
  new: [
    { status: "in_progress", label: "I'm handling this", tone: "secondary" },
    { status: "resolved", label: "Mark as resolved", tone: "primary" },
  ],
  in_progress: [
    { status: "resolved", label: "Mark as resolved", tone: "primary" },
    { status: "new", label: "Move back to new", tone: "secondary" },
  ],
  resolved: [{ status: "new", label: "Reopen", tone: "secondary" }],
};

export default async function ConversationPage({ params }: {
  params: Promise<{ tenantId: string; conversationId: string }>;
}) {
  const { tenantId, conversationId } = await params;
  requireIds(conversationId);
  const clinic = await loadClinic(tenantId);
  const back = <p><Link href={`/clinics/${tenantId}/inbox`}>← Back to inbox</Link></p>;
  if (!canHandleInbox(clinic.my_role)) {
    return (
      <>
        {back}
        <p className="notice-inline">
          Patient conversations are only available to owners, admins and receptionists.
        </p>
      </>
    );
  }

  const { conversation, messages, handover } =
    await load<ConversationDetail>(tenantId, "conversations", conversationId);
  const state = CONVERSATION_STATE[conversation.status];

  return (
    <>
      {back}
      <h1>Conversation</h1>
      <p>
        <Badge tone={state.tone}>{state.label}</Badge>{" "}
        <span className="muted">
          Started {formatDate(conversation.started_at)}
          {conversation.origin_host ? ` on ${conversation.origin_host}` : ""}
        </span>
      </p>

      {handover && (
        <section className="panel contact-card" aria-labelledby="contact-heading">
          <h2 id="contact-heading">
            Call-back request{" "}
            <Badge tone={HANDOVER_STATE[handover.status].tone}>{HANDOVER_STATE[handover.status].label}</Badge>
          </h2>
          <dl>
            <dt>Name</dt><dd>{handover.contact_name ?? "Not given"}</dd>
            <dt>Phone</dt>
            <dd>{handover.contact_phone ? <a href={`tel:${handover.contact_phone.replace(/[^+\d]/g, "")}`}>{handover.contact_phone}</a> : "Not given"}</dd>
            <dt>Email</dt>
            <dd>{handover.contact_email ? <a href={`mailto:${handover.contact_email}`}>{handover.contact_email}</a> : "Not given"}</dd>
            {handover.note && (<><dt>Note</dt><dd>{handover.note}</dd></>)}
            <dt>Asked</dt><dd>{formatDate(handover.created_at)}</dd>
            {handover.resolved_at && (
              <><dt>Resolved</dt><dd>{formatDate(handover.resolved_at)}{handover.resolved_by_me ? " (by you)" : ""}</dd></>
            )}
          </dl>
          <p className="hint">
            The visitor agreed that the clinic may use these details to contact them about this
            enquiry only.
          </p>
          <div className="button-row">
            {NEXT_STEPS[handover.status].map((step) => (
              <ActionButton key={step.status} tone={step.tone} submitLabel={step.label}
                action={setHandoverStatus.bind(null, tenantId, handover.id, step.status)} />
            ))}
          </div>
        </section>
      )}

      <section className="panel" aria-labelledby="transcript-heading">
        <h2 id="transcript-heading">Transcript</h2>
        {messages.length === 0 ? <p>No messages.</p> : (
          <ol className="transcript">
            {messages.map((m) => (
              <li key={m.id} className={m.role}>
                <span className="sr-only">
                  {m.role === "visitor" ? "Visitor: " : m.role === "assistant" ? "Assistant: " : "Notice: "}
                </span>
                {m.content}
                <span className="meta">
                  {formatDate(m.created_at)}
                  {m.role === "assistant" && m.answer_source
                    ? ` · ${ANSWER_SOURCE[m.answer_source] ?? m.answer_source}` : ""}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>

      {conversation.status !== "closed" && (
        <section className="panel">
          <h2>Close this conversation</h2>
          <p>The visitor will not be able to send more messages in this chat.</p>
          <ActionButton tone="secondary" submitLabel="Close conversation"
            confirmText="Close this conversation? The visitor will need to start a new chat."
            action={closeConversation.bind(null, tenantId, conversation.id)} />
        </section>
      )}
    </>
  );
}
