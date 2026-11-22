import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { NavLink } from "@/components/NavLink";
import { Wordmark } from "@/components/marketing/Wordmark";
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
        <Link href="/dashboard" className="sidebar-logo"><Wordmark size="sm" alt="ZUVOORA Engage — your clinics" /></Link>
        <div className="clinic-name">Platform</div>
        <nav aria-label="Platform sections">
          <NavLink href="/platform" exact>Clinics &amp; plans</NavLink>
          <NavLink href="/platform/plans">Plan catalogue</NavLink>
          <NavLink href="/platform/demo-requests">Demo requests</NavLink>
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
