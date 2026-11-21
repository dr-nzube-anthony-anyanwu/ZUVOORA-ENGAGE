import Link from "next/link";
import { ActionButton, ActionForm } from "@/components/ActionForm";
import { Badge, Field, ReadOnlyNotice } from "@/components/ui";
import { rotateWidgetKey, saveWidgetGreeting, setWidgetEnabled } from "@/lib/actions";
import { load, loadClinic } from "@/lib/clinic";
import { canEdit, type WidgetSettings } from "@/lib/types";

/** Public base URL of the Engage API that serves the widget (server-side setting). */
const PUBLIC_API_URL = (process.env.ENGAGE_PUBLIC_API_URL ?? "http://127.0.0.1:8073").replace(/\/$/, "");

export default async function WidgetPage({ params }: { params: Promise<{ tenantId: string }> }) {
  const { tenantId } = await params;
  const clinic = await loadClinic(tenantId);
  const widget = await load<WidgetSettings>(tenantId, "widget");
  const editable = canEdit(clinic.my_role);
  const snippet =
    `<script src="${PUBLIC_API_URL}/widget/v1/loader.js" data-engage-key="${widget.public_key}" async></script>`;

  return (
    <>
      <h1>Chat widget</h1>
      <p>
        The chat answers patients from your <strong>published</strong> information only. It only
        appears on your verified website domains.
      </p>
      <section className="panel">
        <div className="row-between">
          <h2>Status</h2>
          {widget.enabled ? <Badge tone="good">On</Badge> : <Badge>Off</Badge>}
        </div>
        {widget.verified_hosts.length === 0 ? (
          <p className="notice-inline">
            No verified domain yet. <Link href={`/clinics/${tenantId}/domains`}>Verify your website</Link>{" "}
            before turning the chat on.
          </p>
        ) : (
          <p>Works on: {widget.verified_hosts.map((h) => <code key={h} className="mono">{h} </code>)}</p>
        )}
        {editable && (
          <div className="actions-row">
            {widget.enabled ? (
              <ActionButton action={setWidgetEnabled.bind(null, tenantId, false)} submitLabel="Turn chat off"
                            tone="secondary" confirmText="Turn the chat off on your website?" />
            ) : (
              <ActionButton action={setWidgetEnabled.bind(null, tenantId, true)} submitLabel="Turn chat on" />
            )}
          </div>
        )}
      </section>
      <section className="panel">
        <h2>Add it to your website</h2>
        <p>Paste this snippet just before the closing <code>&lt;/body&gt;</code> tag on your site.</p>
        <pre className="text-preview mono copyable" aria-label="Embed snippet">{snippet}</pre>
        {editable && (
          <div className="actions-row">
            <ActionButton action={rotateWidgetKey.bind(null, tenantId)} submitLabel="Replace key" tone="danger"
                          confirmText="Create a new key? The current snippet stops working until you update your website." />
          </div>
        )}
      </section>
      <section className="panel">
        <h2>Greeting</h2>
        {!editable && <ReadOnlyNotice />}
        <ActionForm action={saveWidgetGreeting.bind(null, tenantId)} submitLabel="Save greeting">
          <fieldset disabled={!editable}>
            <Field label="First message patients see" hint="Plain text, up to 300 characters.">
              <textarea name="greeting" rows={3} maxLength={300} required defaultValue={widget.greeting} />
            </Field>
          </fieldset>
        </ActionForm>
      </section>
    </>
  );
}
