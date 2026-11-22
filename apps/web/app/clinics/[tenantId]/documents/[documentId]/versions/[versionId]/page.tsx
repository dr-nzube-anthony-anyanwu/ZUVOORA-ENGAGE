import Link from "next/link";
import { ActionForm } from "@/components/ActionForm";
import { Badge, Field, formatDate } from "@/components/ui";
import { reviewVersion } from "@/lib/actions";
import { load, loadClinic, requireIds } from "@/lib/clinic";
import { AI_READ_NOTICE, VERSION_STATE } from "@/lib/documents";
import { canEdit, type KnowledgeDocumentDetail, type KnowledgeVersionDetail } from "@/lib/types";

export default async function VersionReviewPage({ params }: {
  params: Promise<{ tenantId: string; documentId: string; versionId: string }>;
}) {
  const { tenantId, documentId, versionId } = await params;
  requireIds(documentId, versionId);
  const clinic = await loadClinic(tenantId);
  const [doc, version] = await Promise.all([
    load<KnowledgeDocumentDetail>(tenantId, "knowledge", documentId),
    load<KnowledgeVersionDetail>(tenantId, "knowledge", documentId, "versions", versionId),
  ]);
  const editable = canEdit(clinic.my_role) && doc.state !== "archived";
  const canApprove = editable && (version.status === "extracted"
    || (version.status === "approved" && !version.is_published));

  return (
    <>
      <p><Link href={`/clinics/${tenantId}/documents/${doc.id}`}>← {doc.title}</Link></p>
      <h1>Version {version.version_no}</h1>
      <section className="panel">
        <div className="row-between">
          <Badge tone={VERSION_STATE[version.status].tone}>{VERSION_STATE[version.status].label}</Badge>
          <span className="hint">{version.file_name} · uploaded {formatDate(version.uploaded_at)}</span>
        </div>
        <p>
          This is exactly the text the assistant will be able to quote once approved. Check that
          it is accurate, current and contains no patient information or medical advice.
        </p>
        {version.extraction_method === "vision" && (
          <p role="note" className="notice-inline"><Badge tone="warn">Read by AI</Badge> {AI_READ_NOTICE}</p>
        )}
        <pre className="text-preview" tabIndex={0} aria-label="Extracted text">
          {version.extracted_text}
        </pre>
      </section>
      {(canApprove || (editable && version.status === "extracted")) && (
        <section className="panel">
          <h2>Decision</h2>
          <div className="grid-2">
            {canApprove && (
              <ActionForm action={reviewVersion.bind(null, tenantId, doc.id, version.id, "approve")}
                          submitLabel="Approve and publish">
                <Field label="Note (optional)">
                  <input name="note" maxLength={500} placeholder="e.g. Checked against current price list" />
                </Field>
              </ActionForm>
            )}
            {version.status === "extracted" && (
              <ActionForm action={reviewVersion.bind(null, tenantId, doc.id, version.id, "reject")}
                          submitLabel="Reject" tone="danger">
                <Field label="Reason (optional)">
                  <input name="note" maxLength={500} placeholder="e.g. Out of date" />
                </Field>
              </ActionForm>
            )}
          </div>
        </section>
      )}
    </>
  );
}
