import { Badge, formatDate } from "@/components/ui";
import { load, loadClinic } from "@/lib/clinic";
import {
  LIMIT_LABELS, canEdit, type ClinicPlan, type SubscriptionStatus, type Usage, type UsageItem,
} from "@/lib/types";

function UsageTable({ items }: { items: UsageItem[] }) {
  return (
    <table className="table">
      <tbody>
        {items.map((item) => {
          const share = item.limit ? Math.min(item.used / item.limit, 1) : 0;
          const shown = item.key === "ai_usd" ? item.used.toFixed(2) : item.used.toLocaleString("en-GB");
          return (
            <tr key={item.key}>
              <td>{item.label}</td>
              <td className="usage-cell">
                <span>{shown}{item.limit !== null ? ` of ${item.limit.toLocaleString("en-GB")}` : ""}</span>
                {item.limit !== null && (
                  <progress value={share} max={1} aria-label={`${item.label}: ${Math.round(share * 100)}% used`}
                    className={share >= 1 ? "full" : share >= 0.8 ? "high" : undefined} />
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

const STATUS: Record<SubscriptionStatus, { label: string; tone: string }> = {
  trialing: { label: "Trial", tone: "warn" },
  active: { label: "Active", tone: "good" },
  past_due: { label: "Payment overdue", tone: "bad" },
  cancelled: { label: "Cancelled", tone: "bad" },
};

export default async function PlanPage({ params }: { params: Promise<{ tenantId: string }> }) {
  const { tenantId } = await params;
  const clinic = await loadClinic(tenantId);
  if (!canEdit(clinic.my_role)) {
    return (
      <>
        <h1>Plan &amp; usage</h1>
        <p className="notice-inline">The clinic&apos;s plan is visible to owners and admins.</p>
      </>
    );
  }
  const [plan, usage] = await Promise.all([
    load<ClinicPlan>(tenantId, "plan"),
    load<Usage>(tenantId, "usage"),
  ]);
  const status = STATUS[plan.status];

  return (
    <>
      <h1>Plan &amp; usage</h1>
      <section className="panel">
        <div className="row-between">
          <h2>{plan.plan_name}</h2>
          <Badge tone={status.tone}>{status.label}</Badge>
        </div>
        {plan.current_period_end && (
          <p className="muted">
            {plan.status === "trialing" ? "Trial ends" : "Current period ends"} {formatDate(plan.current_period_end)}
          </p>
        )}
        {plan.status === "cancelled" && (
          <p className="notice-inline">
            The subscription is cancelled: the website chat is off. Your information is kept;
            contact ZUVOORA to reactivate.
          </p>
        )}
        <p>To change plan, contact ZUVOORA. Your clinic&apos;s information and website chat stay the same.</p>
      </section>

      <section className="panel" aria-labelledby="usage-heading">
        <h2 id="usage-heading">This month ({usage.period})</h2>
        <UsageTable items={usage.monthly} />
        <p className="hint">
          At a monthly limit, AI answers or new online bookings pause until next month. Emergency
          guidance, call-back requests and emails about existing bookings always continue.
        </p>
        <h3>Now</h3>
        <UsageTable items={usage.totals} />
      </section>

      <section className="panel">
        <h2>What&apos;s included</h2>
        <table className="table">
          <tbody>
            {plan.features.map((f) => (
              <tr key={f.key}>
                <td>{f.name}</td>
                <td>
                  {!f.included ? <Badge>Not in this plan</Badge>
                    : !f.available ? <Badge tone="warn">Included — not yet available</Badge>
                    : <Badge tone="good">Included</Badge>}
                </td>
                <td className="muted small">{f.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="panel">
        <h2>Limits</h2>
        <table className="table">
          <tbody>
            {Object.entries(LIMIT_LABELS).map(([key, label]) => (
              <tr key={key}>
                <td>{label}</td>
                <td>{plan.limits[key] !== undefined ? plan.limits[key].toLocaleString("en-GB") : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
