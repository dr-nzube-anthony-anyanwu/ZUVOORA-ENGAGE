import { ActionButton, ActionForm } from "@/components/ActionForm";
import { Badge, Field, formatDate } from "@/components/ui";
import { changeMemberRole, inviteMember, revokeMember } from "@/lib/actions";
import { load, loadClinic } from "@/lib/clinic";
import { ROLE_LABEL, canEdit, type Member } from "@/lib/types";
import type { Role } from "@/lib/api";

const ROLE_HELP: Record<Role, string> = {
  owner: "Everything, including managing owners.",
  admin: "Edit and publish content, manage domains and staff (not owners).",
  receptionist: "Read-only access to clinic content.",
  viewer: "Read-only access to clinic content.",
};

export default async function TeamPage({ params }: { params: Promise<{ tenantId: string }> }) {
  const { tenantId } = await params;
  const clinic = await loadClinic(tenantId);
  if (!canEdit(clinic.my_role)) {
    return (
      <>
        <h1>Team</h1>
        <section className="panel"><p>Only owners and admins can view and manage the team.</p></section>
      </>
    );
  }
  const members = await load<Member[]>(tenantId, "members");
  const isOwner = clinic.my_role === "owner";
  const grantable: Role[] = isOwner
    ? ["owner", "admin", "receptionist", "viewer"]
    : ["admin", "receptionist", "viewer"];

  return (
    <>
      <h1>Team</h1>
      <p>People who can sign in to this clinic&apos;s workspace. Patients never sign in here.</p>
      <section className="panel">
        <table className="table">
          <thead>
            <tr><th scope="col">Email</th><th scope="col">Role</th><th scope="col">Since</th>
              <th scope="col"><span className="sr-only">Actions</span></th></tr>
          </thead>
          <tbody>
            {members.map((m) => {
              const manageable = m.is_active && (isOwner || m.role !== "owner");
              return (
                <tr key={m.membership_id} className={m.is_active ? "" : "muted"}>
                  <td>{m.email ?? "—"}</td>
                  <td>
                    {manageable ? (
                      <ActionForm action={changeMemberRole.bind(null, tenantId, m.membership_id)}
                                  submitLabel="Change" tone="secondary" className="inline-form">
                        <select name="role" defaultValue={m.role} aria-label={`Role for ${m.email ?? "member"}`}>
                          {grantable.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                        </select>
                      </ActionForm>
                    ) : (
                      <>
                        {ROLE_LABEL[m.role]}{" "}
                        {!m.is_active && <Badge tone="bad">Revoked {formatDate(m.revoked_at)}</Badge>}
                      </>
                    )}
                  </td>
                  <td className="muted">{formatDate(m.created_at)}</td>
                  <td>
                    {manageable && (
                      <ActionButton action={revokeMember.bind(null, tenantId, m.membership_id)}
                                    submitLabel="Revoke" tone="danger"
                                    confirmText={`Revoke access for ${m.email ?? "this member"}? It takes effect immediately.`} />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
      <section className="panel">
        <h2>Invite someone</h2>
        <ActionForm action={inviteMember.bind(null, tenantId)} submitLabel="Send invitation">
          <div className="grid-2">
            <Field label="Email">
              <input name="email" type="email" required maxLength={254} autoComplete="off" />
            </Field>
            <Field label="Role">
              <select name="role" defaultValue="receptionist">
                {grantable.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
              </select>
            </Field>
          </div>
          <ul className="hint">
            {grantable.map((r) => <li key={r}><strong>{ROLE_LABEL[r]}:</strong> {ROLE_HELP[r]}</li>)}
          </ul>
        </ActionForm>
      </section>
    </>
  );
}
