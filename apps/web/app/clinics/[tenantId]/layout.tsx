import Link from "next/link";
import type { ReactNode } from "react";
import { apiGet, tenantPath } from "@/lib/api";
import { loadClinic } from "@/lib/clinic";
import { ROLE_LABEL, canHandleInbox, type InboxSummary } from "@/lib/types";

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
        <Link href="/dashboard" className="brand">ZUVOORA ENGAGE</Link>
        <div className="clinic-name">{clinic.tenant.display_name}</div>
        <div className="muted small">{ROLE_LABEL[clinic.my_role]}</div>
        <nav aria-label="Clinic sections">
          {inbox && (
            <Link href={`/clinics/${tenantId}/inbox`}>
              Inbox
              {inbox.new > 0 && (
                <span className="count" aria-label={`${inbox.new} new`}>{inbox.new}</span>
              )}
            </Link>
          )}
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
