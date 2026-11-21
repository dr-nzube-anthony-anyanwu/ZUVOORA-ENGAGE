import Link from "next/link";
import { load, loadClinic } from "@/lib/clinic";
import type {
  BranchContent, ContentItem, Domain, FaqContent, KnowledgeDocument, ProfileContent,
  ServiceContent,
} from "@/lib/types";

type Step = { done: boolean; label: string; detail: string; href: string };

export default async function ClinicOverview({ params }: { params: Promise<{ tenantId: string }> }) {
  const { tenantId } = await params;
  const clinic = await loadClinic(tenantId);
  const [profile, branches, services, faqs, domains, documents] = await Promise.all([
    load<ContentItem<ProfileContent>>(tenantId, "profile"),
    load<ContentItem<BranchContent>[]>(tenantId, "branches"),
    load<ContentItem<ServiceContent>[]>(tenantId, "services"),
    load<ContentItem<FaqContent>[]>(tenantId, "faqs"),
    load<Domain[]>(tenantId, "domains"),
    load<KnowledgeDocument[]>(tenantId, "knowledge"),
  ]);

  const live = <T,>(items: ContentItem<T>[]) => items.filter((i) => i.published !== null).length;
  const withHours = branches.filter((b) => b.published?.opening_hours).length;
  const verified = domains.filter((d) => d.status === "verified").length;
  const liveDocs = documents.filter((d) => d.published_version !== null).length;
  const pendingDocs = documents.reduce((sum, d) => sum + d.awaiting_review, 0);
  const pendingChanges = [profile, ...branches, ...services, ...faqs]
    .filter((i) => i.state === "changes_pending" || i.state === "draft").length;

  const base = `/clinics/${tenantId}`;
  const steps: Step[] = [
    { done: profile.published !== null, label: "Publish your clinic profile",
      detail: "Contact details and what to do in an eye emergency.", href: `${base}/profile` },
    { done: withHours > 0, label: "Add a branch with opening hours",
      detail: `${withHours} live branch${withHours === 1 ? "" : "es"} with hours.`,
      href: `${base}/branches` },
    { done: live(services) > 0, label: "Publish your services",
      detail: `${live(services)} live service${live(services) === 1 ? "" : "s"}.`,
      href: `${base}/services` },
    { done: live(faqs) > 0, label: "Publish common questions",
      detail: `${live(faqs)} live FAQ${live(faqs) === 1 ? "" : "s"}.`, href: `${base}/faqs` },
    { done: liveDocs > 0, label: "Approve a knowledge document (optional)",
      detail: `${liveDocs} live document${liveDocs === 1 ? "" : "s"}.`, href: `${base}/documents` },
    { done: verified > 0, label: "Verify your website domain",
      detail: "Needed before the chat widget can run on your website.", href: `${base}/domains` },
  ];
  const complete = steps.filter((s) => s.done).length;

  return (
    <>
      <h1>{clinic.tenant.display_name}</h1>
      <p>
        Only <strong>published</strong> information will be used to answer patients. Drafts and
        documents awaiting review are never shown to patients.
      </p>
      <section className="panel">
        <h2>Setup checklist · {complete} of {steps.length}</h2>
        <ol className="checklist">
          {steps.map((step) => (
            <li key={step.label} className={step.done ? "done" : ""}>
              <span aria-hidden="true">{step.done ? "✓" : "○"}</span>
              <div>
                <Link href={step.href}>{step.label}</Link>
                <span className="sr-only">{step.done ? " (done)" : " (to do)"}</span>
                <div className="hint">{step.detail}</div>
              </div>
            </li>
          ))}
        </ol>
      </section>
      {(pendingChanges > 0 || pendingDocs > 0) && (
        <section className="panel notice">
          <h2>Waiting for review</h2>
          <ul>
            {pendingChanges > 0 && <li>{pendingChanges} item(s) with unpublished drafts.</li>}
            {pendingDocs > 0 && (
              <li><Link href={`${base}/documents`}>{pendingDocs} document version(s)</Link> to review.</li>
            )}
          </ul>
        </section>
      )}
    </>
  );
}
