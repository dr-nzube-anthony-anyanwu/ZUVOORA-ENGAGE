import { ActionForm } from "@/components/ActionForm";
import { Badge, Field, formatDate } from "@/components/ui";
import { ApiRequestError, apiGet } from "@/lib/api";
import { changeSubscription } from "@/lib/actions";
import type { Catalogue, PlatformOverview, Subscription } from "@/lib/types";

const STATUSES = [
  { key: "trialing", label: "Trial" },
  { key: "active", label: "Active" },
  { key: "past_due", label: "Payment overdue" },
  { key: "cancelled", label: "Cancelled" },
];

export default async function PlatformClinicsPage() {
  let subscriptions: Subscription[];
  let catalogue: Catalogue;
  let overview: PlatformOverview;
  try {
    [subscriptions, catalogue, overview] = await Promise.all([
      apiGet<Subscription[]>("/api/v1/platform/subscriptions"),
      apiGet<Catalogue>("/api/v1/platform/plans"),
      apiGet<PlatformOverview>("/api/v1/platform/analytics"),
    ]);
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 403) {
      return <p className="notice-inline">Platform tools need an MFA-verified platform administrator.</p>;
    }
    throw error;
  }
  const planName = new Map(catalogue.plans.map((p) => [p.key, p.name]));

  return (
    <>
      <h1>Clinics &amp; plans</h1>
      <section className="panel" aria-label="This month">
        <h2>This month</h2>
        <div className="stats">
          <div><strong>{overview.paying_clinics}</strong><span>paying clinics</span></div>
          <div>
            <strong>₦{overview.estimated_monthly_revenue_ngn.toLocaleString("en-GB")}</strong>
            <span>estimated monthly revenue</span>
          </div>
          <div><strong>${overview.ai_cost_usd_this_month.toFixed(2)}</strong><span>AI cost so far</span></div>
        </div>
        <table className="table">
          <thead><tr><th scope="col">Clinic</th><th scope="col">Plan</th><th scope="col">Messages</th>
            <th scope="col">Bookings</th><th scope="col">Emails</th><th scope="col">AI $</th></tr></thead>
          <tbody>
            {overview.clinics.map((c) => (
              <tr key={c.tenant_id}>
                <td>{c.display_name}</td>
                <td>{c.plan_name} · {c.subscription_status}</td>
                <td>{c.messages.toLocaleString("en-GB")} / {(c.limits.messages_month ?? 0).toLocaleString("en-GB")}</td>
                <td>{c.bookings} / {c.limits.bookings_month ?? "—"}</td>
                <td>{c.emails} / {c.limits.emails_month ?? "—"}</td>
                <td>{c.ai_usd.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <p>
        Assign each clinic&apos;s plan. Changing a plan never changes the clinic&apos;s data, website
        chat or widget key. No payment is taken here; prices are for your records.
      </p>
      {subscriptions.map((s) => (
        <section key={s.tenant_id} className="panel" aria-label={s.display_name}>
          <div className="row-between">
            <h2>{s.display_name}</h2>
            <span>
              <Badge tone={s.status === "active" ? "good" : s.status === "cancelled" ? "bad" : "warn"}>
                {planName.get(s.plan_key) ?? s.plan_key} · {STATUSES.find((x) => x.key === s.status)?.label}
              </Badge>
              {s.tenant_status !== "active" && <> <Badge tone="bad">Clinic {s.tenant_status}</Badge></>}
            </span>
          </div>
          {s.current_period_end && <p className="muted small">Period ends {formatDate(s.current_period_end)}</p>}
          <ActionForm action={changeSubscription.bind(null, s.tenant_id)} submitLabel="Save subscription">
            <div className="form-grid">
              <Field label="Plan">
                <select name="plan_key" defaultValue={s.plan_key}>
                  {catalogue.plans.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
                </select>
              </Field>
              <Field label="Status">
                <select name="status" defaultValue={s.status}>
                  {STATUSES.map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}
                </select>
              </Field>
              <Field label="Period end (optional)">
                <input type="date" name="current_period_end"
                  defaultValue={s.current_period_end ? s.current_period_end.slice(0, 10) : ""} />
              </Field>
              <Field label="Agreed monthly price, ₦ (optional)">
                <input type="number" min={0} name="monthly_price_override_ngn"
                  defaultValue={s.monthly_price_override_ngn ?? ""} />
              </Field>
            </div>
            <Field label="Notes (optional)">
              <input name="notes" maxLength={500} defaultValue={s.notes ?? ""} />
            </Field>
          </ActionForm>
        </section>
      ))}
    </>
  );
}
