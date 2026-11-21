import Link from "next/link";
import type { ReactNode } from "react";
import { loadClinic } from "@/lib/clinic";
import { ROLE_LABEL } from "@/lib/types";

export const dynamic = "force-dynamic";

const NAV = [
  { href: "", label: "Overview" },
  { href: "/profile", label: "Clinic profile" },
  { href: "/branches", label: "Branches & hours" },
  { href: "/services", label: "Services" },
  { href: "/faqs", label: "FAQs" },
  { href: "/documents", label: "Documents" },
  { href: "/domains", label: "Website domains" },
  { href: "/team", label: "Team" },
];

export default async function ClinicLayout({
  children, params,
}: { children: ReactNode; params: Promise<{ tenantId: string }> }) {
  const { tenantId } = await params;
  const clinic = await loadClinic(tenantId);
  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="brand">ZUVOORA ENGAGE</Link>
        <div className="clinic-name">{clinic.tenant.display_name}</div>
        <div className="muted small">{ROLE_LABEL[clinic.my_role]}</div>
        <nav aria-label="Clinic sections">
          {NAV.map((item) => (
            <Link key={item.href} href={`/clinics/${tenantId}${item.href}`}>{item.label}</Link>
          ))}
        </nav>
        <form action="/auth/signout" method="post">
          <button type="submit" className="link-button">Sign out</button>
        </form>
      </aside>
      <main className="workspace">
        {clinic.tenant.status === "pending" && (
          <p className="notice-inline">
            This clinic is being set up. Content you publish will be used once the assistant
            goes live.
          </p>
        )}
        {children}
      </main>
    </div>
  );
}
