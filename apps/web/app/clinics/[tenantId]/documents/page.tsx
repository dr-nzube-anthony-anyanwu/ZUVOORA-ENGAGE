import Link from "next/link";
import { ActionForm } from "@/components/ActionForm";
import { Badge, Field, ReadOnlyNotice, formatDate } from "@/components/ui";
import { uploadDocument } from "@/lib/actions";
import { ACCEPT, DOC_STATE } from "@/lib/documents";
import { loadClinic, loadWithQuery } from "@/lib/clinic";
import { canEdit, type KnowledgeDocument } from "@/lib/types";

export default async function DocumentsPage({ params, searchParams }: {
  params: Promise<{ tenantId: string }>;
  searchParams: Promise<{ archived?: string }>;
}) {
  const [{ tenantId }, { archived }] = await Promise.all([params, searchParams]);
  const clinic = await loadClinic(tenantId);
  const showArchived = archived === "1";
  const documents = await loadWithQuery<KnowledgeDocument[]>(
    tenantId, ["knowledge"], showArchived ? { include_archived: "true" } : {},
  );
  const editable = canEdit(clinic.my_role);
  const base = `/clinics/${tenantId}/documents`;

  return (
    <>
      <h1>Documents</h1>
      <p>
        Upload policies, price lists or patient information. We extract the text; an owner or admin
        must read and approve it before the assistant can use it.
      </p>
      <section className="panel">
        {documents.length === 0 ? <p>No documents yet.</p> : (
          <table className="table">
            <thead>
              <tr><th scope="col">Title</th><th scope="col">Status</th><th scope="col">Live version</th>
                <th scope="col">Updated</th></tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id}>
                  <td><Link href={`${base}/${doc.id}`}>{doc.title}</Link></td>
                  <td><Badge tone={DOC_STATE[doc.state].tone}>{DOC_STATE[doc.state].label}</Badge></td>
                  <td>{doc.published_version ? `v${doc.published_version.version_no}` : "—"}</td>
                  <td className="muted">{formatDate(doc.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="hint">
          {showArchived ? <Link href={base}>Hide archived</Link> : <Link href={`${base}?archived=1`}>Show archived</Link>}
        </p>
      </section>
      {editable ? (
        <section className="panel">
          <h2>Upload a document</h2>
          <ActionForm action={uploadDocument.bind(null, tenantId)} submitLabel="Upload">
            <Field label="Title">
              <input name="title" required minLength={2} maxLength={200} placeholder="e.g. Payment and HMO policy" />
            </Field>
            <Field label="File" hint="PDF, Word (.docx), text or Markdown. Up to 10 MB. Scanned images and password-protected files are not supported.">
              <input name="file" type="file" required accept={ACCEPT} />
            </Field>
          </ActionForm>
        </section>
      ) : <ReadOnlyNotice />}
    </>
  );
}
