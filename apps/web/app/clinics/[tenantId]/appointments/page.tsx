import Link from "next/link";
import { ActionButton } from "@/components/ActionForm";
import { Badge, formatDate } from "@/components/ui";
import { cancelAppointment } from "@/lib/actions";
import { loadClinic, loadWithQuery } from "@/lib/clinic";
import { canHandleInbox, type Appointment, type AppointmentStatus } from "@/lib/types";

const VIEWS = [
  { key: "upcoming", label: "Upcoming" },
  { key: "past", label: "Past and cancelled" },
  { key: "all", label: "All" },
] as const;

const STATUS: Record<AppointmentStatus, { label: string; tone: string }> = {
  booking: { label: "Booking…", tone: "neutral" },
  confirmed: { label: "Confirmed", tone: "good" },
  pending: { label: "Needs your confirmation", tone: "warn" },
  unknown: { label: "Being checked with Cal.com", tone: "warn" },
  failed: { label: "Not booked", tone: "bad" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  rescheduled: { label: "Moved", tone: "neutral" },
};

export default async function AppointmentsPage({ params, searchParams }: {
  params: Promise<{ tenantId: string }>;
  searchParams: Promise<{ view?: string }>;
}) {
  const [{ tenantId }, { view: raw }] = await Promise.all([params, searchParams]);
  const clinic = await loadClinic(tenantId);
  const base = `/clinics/${tenantId}/appointments`;
  if (!canHandleInbox(clinic.my_role)) {
    return (
      <>
        <h1>Appointments</h1>
        <p className="notice-inline">
          Patient bookings are only available to owners, admins and receptionists.
        </p>
      </>
    );
  }
  const view = VIEWS.some((v) => v.key === raw) ? raw as (typeof VIEWS)[number]["key"] : "upcoming";
  const appointments = await loadWithQuery<Appointment[]>(tenantId, ["appointments"], { view });

  return (
    <>
      <h1>Appointments</h1>
      <p>
        Bookings made through your website chat. Cancelling here cancels the booking in Cal.com
        first; the patient is emailed.
      </p>
      <nav className="tabs" aria-label="Appointment views">
        {VIEWS.map((v) => (
          <Link key={v.key} href={`${base}?view=${v.key}`} aria-current={v.key === view ? "page" : undefined}>
            {v.label}
          </Link>
        ))}
      </nav>
      <section className="panel">
        {appointments.length === 0 ? <p>No appointments here.</p> : (
          <table className="table">
            <thead>
              <tr><th scope="col">When</th><th scope="col">Type</th><th scope="col">Patient</th>
                <th scope="col">Status</th><th scope="col"><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {appointments.map((a) => (
                <tr key={a.id}>
                  <td>{formatDate(a.start_at)}</td>
                  <td>{a.type_name}</td>
                  <td>
                    <div>{a.attendee_name}</div>
                    <div className="muted small">{a.attendee_email}{a.attendee_phone ? ` · ${a.attendee_phone}` : ""}</div>
                    {a.conversation_id && (
                      <Link prefetch={false} href={`/clinics/${tenantId}/inbox/${a.conversation_id}`} className="small">
                        Chat
                      </Link>
                    )}
                  </td>
                  <td><Badge tone={STATUS[a.status].tone}>{STATUS[a.status].label}</Badge></td>
                  <td>
                    {(a.status === "confirmed" || a.status === "pending") && (
                      <ActionButton tone="danger" submitLabel="Cancel"
                        confirmText={`Cancel the ${a.type_name} for ${a.attendee_name}? Cal.com and the patient will be told.`}
                        action={cancelAppointment.bind(null, tenantId, a.id)} />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
