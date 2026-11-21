import { ActionButton, ActionForm } from "@/components/ActionForm";
import { Badge, Field, ReadOnlyNotice, formatDate } from "@/components/ui";
import { addDomain, removeDomain, verifyDomain } from "@/lib/actions";
import { load, loadClinic } from "@/lib/clinic";
import { canEdit, type Domain } from "@/lib/types";

const RESULT: Record<string, string> = {
  not_found: "Record not found yet",
  mismatch: "Record value does not match",
  dns_error: "DNS lookup failed",
  timeout: "DNS lookup timed out",
};

export default async function DomainsPage({ params }: { params: Promise<{ tenantId: string }> }) {
  const { tenantId } = await params;
  const clinic = await loadClinic(tenantId);
  const domains = await load<Domain[]>(tenantId, "domains");
  const editable = canEdit(clinic.my_role);

  return (
    <>
      <h1>Website domains</h1>
      <p>
        Prove that you control your website so the chat widget can run on it. Add the TXT record
        shown below at your DNS provider (for example Cloudflare), then press Verify.
      </p>
      {domains.length === 0 && <section className="panel"><p>No domains yet.</p></section>}
      {domains.map((domain) => (
        <section className="panel" key={domain.id}>
          <div className="row-between">
            <h2 className="mono">{domain.hostname}</h2>
            {domain.status === "verified"
              ? <Badge tone="good">Verified {formatDate(domain.verified_at)}</Badge>
              : <Badge tone="warn">Not verified</Badge>}
          </div>
          {domain.status !== "verified" && (
            <>
              <dl className="details">
                <div><dt>Type</dt><dd className="mono">TXT</dd></div>
                <div><dt>Name / Host</dt><dd className="mono copyable">{domain.dns_record.name}</dd></div>
                <div><dt>Value</dt><dd className="mono copyable">{domain.dns_record.value}</dd></div>
              </dl>
              <p className="hint">
                Some DNS providers add your domain automatically: if so, enter only the part before
                your domain in the Name field. Last check: {formatDate(domain.last_checked_at)}
                {domain.last_check_result && domain.last_check_result !== "verified"
                  ? ` — ${RESULT[domain.last_check_result]}` : ""}.
              </p>
            </>
          )}
          {editable && (
            <div className="actions-row">
              {domain.status !== "verified" && (
                <ActionButton action={verifyDomain.bind(null, tenantId, domain.id)} submitLabel="Verify" />
              )}
              <ActionButton action={removeDomain.bind(null, tenantId, domain.id)} submitLabel="Remove"
                            tone="danger"
                            confirmText={`Remove ${domain.hostname}? The widget will stop working on it.`} />
            </div>
          )}
        </section>
      ))}
      {editable ? (
        <section className="panel">
          <h2>Add a domain</h2>
          <ActionForm action={addDomain.bind(null, tenantId)} submitLabel="Add domain">
            <Field label="Website host name" hint="For example www.yourclinic.com — no https:// or page path.">
              <input name="hostname" required maxLength={253} placeholder="www.yourclinic.com"
                     autoComplete="off" spellCheck={false} />
            </Field>
          </ActionForm>
        </section>
      ) : <ReadOnlyNotice />}
    </>
  );
}
