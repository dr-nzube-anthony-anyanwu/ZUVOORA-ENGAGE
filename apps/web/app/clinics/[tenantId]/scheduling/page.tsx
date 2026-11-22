import { ActionButton, ActionForm } from "@/components/ActionForm";
import { Badge, Field, ReadOnlyNotice, formatDate } from "@/components/ui";
import { ApiRequestError, apiGet, tenantPath } from "@/lib/api";
import { connectScheduling, disconnectScheduling, saveAppointmentTypes } from "@/lib/actions";
import { load, loadClinic } from "@/lib/clinic";
import { canEdit, type ProviderEventType, type SchedulingSettings } from "@/lib/types";

/** The provider's appointment types, or a message when the provider cannot be reached. */
async function providerTypes(tenantId: string): Promise<ProviderEventType[] | string> {
  try {
    return await apiGet<ProviderEventType[]>(tenantPath(tenantId, "scheduling", "provider-event-types"));
  } catch (error) {
    if (error instanceof ApiRequestError) return error.userMessage;
    return "Cal.com could not be reached. Please try again.";
  }
}

export default async function SchedulingPage({ params }: { params: Promise<{ tenantId: string }> }) {
  const { tenantId } = await params;
  const clinic = await loadClinic(tenantId);
  const settings = await load<SchedulingSettings>(tenantId, "scheduling");
  const editable = canEdit(clinic.my_role);
  const connection = settings.connection;
  const types = editable && connection ? await providerTypes(tenantId) : null;
  const names = new Map(settings.appointment_types.map((t) => [t.provider_event_type_id, t.name]));

  return (
    <>
      <h1>Scheduling</h1>
      <p>
        Connect your Cal.com account so patients can book from the chat. Bookings are confirmed
        only after Cal.com confirms them.
      </p>

      <section className="panel">
        <div className="row-between">
          <h2>Cal.com account</h2>
          {connection
            ? connection.status === "active" ? <Badge tone="good">Connected</Badge> : <Badge tone="bad">Needs attention</Badge>
            : <Badge>Not connected</Badge>}
        </div>
        {connection ? (
          <>
            <p>
              Account <strong>{connection.account_label ?? "—"}</strong>
              {connection.account_time_zone ? ` · ${connection.account_time_zone}` : ""} · key ending
              <code className="mono"> …{connection.credential_hint}</code> · connected {formatDate(connection.connected_at)}
            </p>
            {connection.status === "failing" && (
              <p className="notice-inline">
                Cal.com no longer accepts this key. Disconnect, create a new API key in Cal.com and
                connect again.
              </p>
            )}
            {editable && (
              <ActionButton action={disconnectScheduling.bind(null, tenantId)} submitLabel="Disconnect"
                tone="danger" confirmText="Disconnect Cal.com? Patients will no longer be able to book from the chat." />
            )}
          </>
        ) : editable ? (
          <ActionForm action={connectScheduling.bind(null, tenantId)} submitLabel="Connect Cal.com">
            <Field label="Cal.com API key"
              hint="In Cal.com open Settings → Security → API keys and create a key. We check it with Cal.com, store it encrypted and never show it again.">
              <input name="api_key" type="password" required minLength={10} maxLength={300}
                autoComplete="off" spellCheck={false} data-gramm="false" data-lpignore="true" />
            </Field>
          </ActionForm>
        ) : <ReadOnlyNotice />}
      </section>

      {connection && (
        <section className="panel">
          <h2>Appointment types patients can book</h2>
          {!editable ? (
            settings.appointment_types.length === 0 ? <p>None offered yet.</p> : (
              <ul>
                {settings.appointment_types.filter((t) => t.enabled).map((t) => (
                  <li key={t.id}>{t.name} · {t.duration_minutes} min</li>
                ))}
              </ul>
            )
          ) : typeof types === "string" ? (
            <p className="notice-inline">{types}</p>
          ) : types && types.length === 0 ? (
            <p>Your Cal.com account has no event types yet. Create one in Cal.com, then reload.</p>
          ) : types && (
            <ActionForm action={saveAppointmentTypes.bind(null, tenantId)} submitLabel="Save appointment types">
              <table className="table">
                <thead>
                  <tr><th scope="col">Offer</th><th scope="col">Name patients see</th>
                    <th scope="col">Length</th><th scope="col">Notes</th></tr>
                </thead>
                <tbody>
                  {types.map((t) => (
                    <tr key={t.id}>
                      <td>
                        <input type="hidden" name="type_id" value={t.id} />
                        <input type="checkbox" name={`offer:${t.id}`} defaultChecked={t.offered}
                          aria-label={`Offer ${t.name}`} />
                      </td>
                      <td>
                        <input name={`name:${t.id}`} defaultValue={names.get(t.id) ?? t.name} maxLength={120}
                          aria-label={`Name patients see for ${t.name}`} />
                      </td>
                      <td>{t.duration_minutes} min</td>
                      <td className="muted">
                        {t.requires_confirmation ? "You confirm each booking in Cal.com. " : ""}
                        {t.hidden ? "Hidden on your Cal.com page." : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ActionForm>
          )}
        </section>
      )}
    </>
  );
}
