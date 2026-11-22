import Link from "next/link";
import { ApiRequestError, apiGet, tenantPath } from "@/lib/api";
import { loadClinic } from "@/lib/clinic";
import { canEdit, type Analytics } from "@/lib/types";

const PERIODS = [7, 30, 90];
const SOURCES: Record<string, string> = {
  facts: "From your published information",
  retrieval_ai: "AI answer from your content",
  fallback: "Could not answer (offered the team)",
  emergency: "Emergency guidance",
  booking: "Booking messages",
  budget_exhausted: "AI limit reached",
};
const BOOKINGS: Record<string, string> = {
  confirmed: "Confirmed", pending: "Awaiting confirmation", cancelled: "Cancelled",
  rescheduled: "Moved", failed: "Not booked", unknown: "Being checked",
};

function Bars({ rows }: { rows: [string, number][] }) {
  const max = Math.max(1, ...rows.map(([, n]) => n));
  return (
    <table className="table">
      <tbody>
        {rows.map(([label, n]) => (
          <tr key={label}>
            <td>{label}</td>
            <td className="usage-cell">
              <span>{n.toLocaleString("en-GB")}</span>
              <progress value={n} max={max} aria-label={`${label}: ${n}`} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);

export default async function AnalyticsPage({ params, searchParams }: {
  params: Promise<{ tenantId: string }>;
  searchParams: Promise<{ days?: string }>;
}) {
  const [{ tenantId }, { days: raw }] = await Promise.all([params, searchParams]);
  const clinic = await loadClinic(tenantId);
  const base = `/clinics/${tenantId}/analytics`;
  if (!canEdit(clinic.my_role)) {
    return <><h1>Analytics</h1><p className="notice-inline">Analytics are for owners and admins.</p></>;
  }
  const days = PERIODS.includes(Number(raw)) ? Number(raw) : 30;
  let data: Analytics;
  try {
    data = await apiGet<Analytics>(`${tenantPath(tenantId, "analytics")}?days=${days}`);
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 403) {
      return <><h1>Analytics</h1><p className="notice-inline">{error.userMessage}</p></>;
    }
    throw error;
  }

  return (
    <>
      <h1>Analytics</h1>
      <nav className="tabs" aria-label="Period">
        {PERIODS.map((d) => (
          <Link key={d} href={`${base}?days=${d}`} aria-current={d === days ? "page" : undefined}>Last {d} days</Link>
        ))}
      </nav>
      <section className="panel" aria-label="Summary">
        <div className="stats">
          <div><strong>{data.conversations}</strong><span>conversations</span></div>
          <div><strong>{data.visitor_messages}</strong><span>patient messages</span></div>
          <div><strong>{data.handovers.total}</strong><span>call-back requests</span></div>
          <div>
            <strong>{data.handovers.median_hours_to_resolve ?? "—"}</strong>
            <span>median hours to resolve</span>
          </div>
        </div>
      </section>
      <section className="panel" aria-label="How questions were answered">
        <h2>How questions were answered</h2>
        <Bars rows={Object.entries(data.answers).map(([k, n]) => [SOURCES[k] ?? k, n])} />
      </section>
      <section className="panel" aria-label="Bookings">
        <h2>Bookings</h2>
        {Object.keys(data.bookings).length === 0 ? <p>No bookings in this period.</p>
          : <Bars rows={Object.entries(data.bookings).map(([k, n]) => [BOOKINGS[k] ?? k, n])} />}
      </section>
      {data.full ? (
        <>
          <section className="panel" aria-label="Rates and AI">
            <h2>Rates and AI</h2>
            <div className="stats">
              <div><strong>{pct(data.full.cancellation_rate)}</strong><span>bookings cancelled</span></div>
              <div><strong>{pct(data.full.reschedule_rate)}</strong><span>bookings moved</span></div>
              <div><strong>{pct(data.full.ai_answer_share)}</strong><span>answers written by AI</span></div>
              <div><strong>${data.full.ai_cost_usd.toFixed(2)}</strong><span>AI cost ({data.full.ai_calls} calls)</span></div>
            </div>
          </section>
          <section className="panel" aria-label="Unanswered topics">
            <h2>Topics the assistant could not answer</h2>
            <p className="hint">
              Words that appeared in at least two unanswered questions. Consider adding an FAQ for them.
              Individual questions are not shown here.
            </p>
            {data.full.unanswered_topics.length === 0 ? <p>None yet.</p>
              : <Bars rows={data.full.unanswered_topics.map((t) => [t.term, t.count])} />}
          </section>
          <section className="panel" aria-label="Daily activity">
            <h2>Daily activity</h2>
            <table className="table">
              <thead><tr><th scope="col">Day</th><th scope="col">Conversations</th><th scope="col">Messages</th>
                <th scope="col">Call-backs</th><th scope="col">Bookings</th></tr></thead>
              <tbody>
                {[...data.full.daily].reverse().map((d) => (
                  <tr key={d.day}><td>{d.day}</td><td>{d.conversations}</td><td>{d.visitor_messages}</td>
                    <td>{d.handovers}</td><td>{d.bookings}</td></tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : (
        <p className="notice-inline">
          Daily trends, booking rates, AI cost and unanswered topics are included from the Professional plan.
        </p>
      )}
    </>
  );
}
