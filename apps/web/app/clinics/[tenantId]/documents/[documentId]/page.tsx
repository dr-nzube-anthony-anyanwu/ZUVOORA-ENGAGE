import Link from "next/link";
import { ActionButton, ActionForm } from "@/components/ActionForm";
import { Badge, Field, ReadOnlyNotice, formatBytes, formatDate } from "@/components/ui";
import { documentAction, renameDocument, uploadVersion } from "@/lib/actions";
import { load, loadClinic, requireIds } from "@/lib/clinic";
import { ACCEPT, DOC_STATE, VERSION_STATE } from "@/lib/documents";
import { canEdit, type KnowledgeDocumentDetail } from "@/lib/types";

const TYPE_LABEL = { pdf: "PDF", docx: "Word", text: "Text" } as const;

export default async function DocumentPage({ params }: {
  params: Promise<{ tenantId: string; documentId: string }>;
}) {
  const { tenantId, documentId } = await params;
  requireIds(documentId);
  const clinic = await loadClinic(tenantId);
  const doc = await load<KnowledgeDocumentDetail>(tenantId, "knowledge", documentId);
  const editable = canEdit(clinic.my_role);
  const archived = doc.state === "archived";
  const base = `/clinics/${tenantId}/documents/${doc.id}`;

  return (
    <>
      <p><Link href={`/clinics/${tenantId}/documents`}>← Documents</Link></p>
      <h1>{doc.title}</h1>
      <section className="panel">
        <div className="row-between">
          <Badge tone={DOC_STATE[doc.state].tone}>{DOC_STATE[doc.state].label}</Badge>
          <span className="hint">
            {doc.published_version
              ? `Version ${doc.published_version.version_no} is live`
              : "No version is live"}
          </span>
        </div>
        <table className="table">
          <thead>
            <tr><th scope="col">Version</th><th scope="col">File</th><th scope="col">Status</th>
              <th scope="col">Uploaded</th><th scope="col"><span className="sr-only">Actions</span></th></tr>
          </thead>
          <tbody>
            {doc.versions.map((v) => (
              <tr key={v.id}>
                <td>v{v.version_no}{v.is_published && <> <Badge tone="good">Live</Badge></>}</td>
                <td>
                  {v.file_name}
                  <div className="hint">
                    {TYPE_LABEL[v.detected_type]} · {formatBytes(v.size_bytes)}
                    {v.page_count ? ` · ${v.page_count} page(s)` : ""}
                    {v.text_length ? ` · ${v.text_length.toLocaleString("en-GB")} characters` : ""}
                  </div>
                </td>
                <td>
                  <Badge tone={VERSION_STATE[v.status].tone}>{VERSION_STATE[v.status].label}</Badge>
                  {v.review_note && <div className="hint">“{v.review_note}”</div>}
                </td>
                <td className="muted">{formatDate(v.uploaded_at)}</td>
                <td>
                  <Link href={`${base}/versions/${v.id}`}>
                    {v.status === "extracted" && editable ? "Review" : "View text"}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {editable ? (
        <>
          {!archived && (
            <section className="panel">
              <h2>Upload a new version</h2>
              <p className="hint">The live version stays live until you review and approve the new one.</p>
              <ActionForm action={uploadVersion.bind(null, tenantId, doc.id)} submitLabel="Upload version">
                <Field label="File" hint="PDF, Word (.docx), text or Markdown. Up to 10 MB.">
                  <input name="file" type="file" required accept={ACCEPT} />
                </Field>
              </ActionForm>
            </section>
          )}
          <section className="panel">
            <h2>Manage</h2>
            {!archived && (
              <ActionForm action={renameDocument.bind(null, tenantId, doc.id)} submitLabel="Rename">
                <Field label="Title">
                  <input name="title" required minLength={2} maxLength={200} defaultValue={doc.title} />
                </Field>
              </ActionForm>
            )}
            <div className="actions-row">
              {doc.published_version && (
                <ActionButton action={documentAction.bind(null, tenantId, doc.id, "unpublish")}
                              submitLabel="Unpublish" tone="secondary"
                              confirmText="Stop the assistant using this document?" />
              )}
              {archived
                ? <ActionButton action={documentAction.bind(null, tenantId, doc.id, "restore")}
                                submitLabel="Restore" tone="secondary" />
                : <ActionButton action={documentAction.bind(null, tenantId, doc.id, "archive")}
                                submitLabel="Archive" tone="danger"
                                confirmText="Archive this document? It will be unpublished." />}
            </div>
          </section>
        </>
      ) : <ReadOnlyNotice />}
    </>
  );
}
