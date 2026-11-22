import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { ApiRequestError, apiGet, type Me } from "@/lib/api";

export const dynamic = "force-dynamic";

/** Platform administration (ZubeVision staff). The API enforces MFA platform-admin access. */
export default async function PlatformLayout({ children }: { children: ReactNode }) {
  let me: Me;
  try {
    me = await apiGet<Me>("/api/v1/me");
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 401) redirect("/login");
    throw error;
  }
  if (!me.is_platform_admin) redirect("/dashboard");
  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="brand">ZUVOORA ENGAGE</Link>
        <div className="clinic-name">Platform</div>
        <nav aria-label="Platform sections">
          <Link href="/platform">Clinics &amp; plans</Link>
          <Link href="/platform/plans">Plan catalogue</Link>
        </nav>
      </aside>
      <main className="workspace">
        {!me.mfa_verified && (
          <p className="notice-inline">
            Platform tools need two-factor authentication. <Link href="/mfa">Verify now</Link>.
          </p>
        )}
        {children}
      </main>
    </div>
  );
}
