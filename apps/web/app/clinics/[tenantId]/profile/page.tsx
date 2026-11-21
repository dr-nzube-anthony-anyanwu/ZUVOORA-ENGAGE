import { ActionButton, ActionForm } from "@/components/ActionForm";
import { Field, ReadOnlyNotice, StateBadge, formatDate } from "@/components/ui";
import { profileAction, saveProfile } from "@/lib/actions";
import { load, loadClinic } from "@/lib/clinic";
import { canEdit, type ContentItem, type ProfileContent } from "@/lib/types";

export default async function ProfilePage({ params }: { params: Promise<{ tenantId: string }> }) {
  const { tenantId } = await params;
  const clinic = await loadClinic(tenantId);
  const profile = await load<ContentItem<ProfileContent>>(tenantId, "profile");
  const editable = canEdit(clinic.my_role);
  const d = profile.draft;

  return (
    <>
      <h1>Clinic profile</h1>
      <p>
        General information the assistant can share. It never gives medical advice; the emergency
        guidance tells patients where to go instead.
      </p>
      <section className="panel">
        <div className="row-between">
          <StateBadge state={profile.state} />
          <span className="hint">Last published: {formatDate(profile.published_at)}</span>
        </div>
        {!editable && <ReadOnlyNotice />}
        <ActionForm action={saveProfile.bind(null, tenantId, profile.revision)}
                    submitLabel="Save draft">
          <fieldset disabled={!editable}>
            <Field label="About the clinic" hint="Up to 2,000 characters. Plain text.">
              <textarea name="about" rows={5} maxLength={2000} defaultValue={d.about ?? ""} />
            </Field>
            <div className="grid-2">
              <Field label="Public phone">
                <input name="public_phone" defaultValue={d.public_phone ?? ""} maxLength={30}
                       placeholder="+234 801 234 5678" />
              </Field>
              <Field label="Public email">
                <input name="public_email" type="email" defaultValue={d.public_email ?? ""}
                       maxLength={254} />
              </Field>
            </div>
            <Field label="Website">
              <input name="website_url" type="url" defaultValue={d.website_url ?? ""}
                     placeholder="https://www.yourclinic.com" maxLength={300} />
            </Field>
            <Field label="Eye emergency guidance"
                   hint="Shown when a patient describes an urgent problem, e.g. sudden vision loss or an eye injury.">
              <textarea name="emergency_guidance" rows={3} maxLength={500}
                        defaultValue={d.emergency_guidance ?? ""} />
            </Field>
          </fieldset>
        </ActionForm>
        {editable && (
          <div className="actions-row">
            {profile.state !== "published" && (
              <ActionButton action={profileAction.bind(null, tenantId, "publish", profile.revision)}
                            submitLabel={`Publish revision ${profile.revision}`} />
            )}
            {profile.published && (
              <ActionButton action={profileAction.bind(null, tenantId, "unpublish", profile.revision)}
                            submitLabel="Unpublish" tone="secondary"
                            confirmText="Remove the clinic profile from what patients can see?" />
            )}
          </div>
        )}
      </section>
      {profile.state === "changes_pending" && profile.published && (
        <section className="panel">
          <h2>Currently live (revision {profile.published_revision})</h2>
          <dl className="details">
            <dt>About</dt><dd>{profile.published.about ?? "—"}</dd>
            <dt>Phone</dt><dd>{profile.published.public_phone ?? "—"}</dd>
            <dt>Email</dt><dd>{profile.published.public_email ?? "—"}</dd>
            <dt>Website</dt><dd>{profile.published.website_url ?? "—"}</dd>
            <dt>Emergency guidance</dt><dd>{profile.published.emergency_guidance ?? "—"}</dd>
          </dl>
        </section>
      )}
    </>
  );
}
