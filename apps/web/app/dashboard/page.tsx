import Link from "next/link";
import { redirect } from "next/navigation";
import { apiGet, ApiRequestError, type Me } from "@/lib/api";

export const dynamic = "force-dynamic";

const ROLE_LABEL: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  receptionist: "Receptionist",
  viewer: "Viewer",
};

export default async function DashboardPage() {
  let me: Me;
  try {
    me = await apiGet<Me>("/api/v1/me");
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 401) redirect("/login");
    return (
      <main>
        <h1>Dashboard</h1>
        <section className="panel">
          <p role="alert" className="error">The Engage service is unavailable. Please try again shortly.</p>
        </section>
      </main>
    );
  }

  return (
    <main>
      <div className="topbar">
        <div className="brand">ZUVOORA ENGAGE</div>
        <form action="/auth/signout" method="post">
          <button type="submit" className="link-button">Sign out</button>
        </form>
      </div>
      <h1>Your clinics</h1>
      <p>Signed in as {me.email}</p>

      {!me.mfa_verified && (
        <section className="panel notice">
          <p>
            Two-factor authentication is not active for this session.{" "}
            <Link href="/mfa">Set up or verify two-factor authentication</Link>. It is required for
            ZubeVision platform administrators.
          </p>
        </section>
      )}

      {me.is_platform_admin && (
        <section className="panel">
          <span className="status">Platform administrator</span>
          <p><Link href="/platform">Open platform tools</Link>: clinics, plans and the plan catalogue.</p>
        </section>
      )}

      <section className="panel">
        {me.memberships.length === 0 ? (
          <p>You are not a member of any clinic yet.</p>
        ) : (
          <ul className="list">
            {me.memberships.map((m) => (
              <li key={m.tenant_id}>
                {m.accessible ? (
                  <Link href={`/clinics/${m.tenant_id}`}><strong>{m.tenant_display_name}</strong></Link>
                ) : (
                  <strong>{m.tenant_display_name ?? "Unavailable clinic"}</strong>
                )}
                <span className="muted"> · {ROLE_LABEL[m.role]}</span>
                {!m.accessible && (
                  <span className="status warn">
                    {m.membership_active ? "Clinic suspended" : "Access revoked"}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
