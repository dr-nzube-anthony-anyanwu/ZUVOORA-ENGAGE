import Link from "next/link";
import type { ReactNode } from "react";
import { NavLink } from "@/components/NavLink";
import { Wordmark } from "@/components/marketing/Wordmark";
import { apiGet, tenantPath } from "@/lib/api";
import { loadClinic } from "@/lib/clinic";
import { ROLE_LABEL, canEdit, canHandleInbox, type InboxSummary } from "@/lib/types";

/** The inbox badge is a convenience: if it cannot load, the page still renders. */
async function inboxSummary(tenantId: string): Promise<InboxSummary | null> {
  try {
    return await apiGet<InboxSummary>(tenantPath(tenantId, "inbox", "summary"));
  } catch {
    return { new: 0, in_progress: 0, open_conversations: 0 };
  }
}

export const dynamic = "force-dynamic";

const NAV = [
  { href: "", label: "Overview" },
  { href: "/profile", label: "Clinic profile" },
  { href: "/branches", label: "Branches & hours" },
  { href: "/services", label: "Services" },
  { href: "/faqs", label: "FAQs" },
  { href: "/documents", label: "Documents" },
  { href: "/domains", label: "Website domains" },
  { href: "/widget", label: "Chat widget" },
  { href: "/scheduling", label: "Scheduling" },
  { href: "/team", label: "Team" },
];

export default async function ClinicLayout({
  children, params,
}: { children: ReactNode; params: Promise<{ tenantId: string }> }) {
  const { tenantId } = await params;
  const clinic = await loadClinic(tenantId);
  const inbox = canHandleInbox(clinic.my_role) ? await inboxSummary(tenantId) : null;
  return (
    <div className="shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="sidebar-logo"><Wordmark size="sm" alt="ZUVOORA Engage — your clinics" /></Link>
        <div className="clinic-name">{clinic.tenant.display_name}</div>
        <div className="muted small">{ROLE_LABEL[clinic.my_role]}</div>
        <nav aria-label="Clinic sections">
          {inbox && (
            <NavLink href={`/clinics/${tenantId}/inbox`}>
              Inbox
              {inbox.new > 0 && (
                <span className="count" aria-label={`${inbox.new} new`}>{inbox.new}</span>
              )}
            </NavLink>
          )}
          {inbox && <NavLink href={`/clinics/${tenantId}/appointments`}>Appointments</NavLink>}
          {NAV.map((item) => (
            <NavLink key={item.href} href={`/clinics/${tenantId}${item.href}`} exact={item.href === ""}>
              {item.label}
            </NavLink>
          ))}
          {canEdit(clinic.my_role) && <NavLink href={`/clinics/${tenantId}/analytics`}>Analytics</NavLink>}
          {canEdit(clinic.my_role) && <NavLink href={`/clinics/${tenantId}/plan`}>Plan &amp; usage</NavLink>}
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
