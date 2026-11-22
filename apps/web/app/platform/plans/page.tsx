import { ActionForm } from "@/components/ActionForm";
import { Badge, Field } from "@/components/ui";
import { ApiRequestError, apiGet } from "@/lib/api";
import { updatePlan } from "@/lib/actions";
import { LIMIT_LABELS, type Catalogue } from "@/lib/types";

export default async function PlanCataloguePage() {
  let catalogue: Catalogue;
  try {
    catalogue = await apiGet<Catalogue>("/api/v1/platform/plans");
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 403) {
      return <p className="notice-inline">Platform tools need an MFA-verified platform administrator.</p>;
    }
    throw error;
  }
  const featureName = new Map(catalogue.features.map((f) => [f.key, f]));

  return (
    <>
      <h1>Plan catalogue</h1>
      <p>Prices are for your records (no payment is taken). Limits apply to every clinic on the plan.</p>
      {catalogue.plans.map((plan) => (
        <section key={plan.key} className="panel" aria-label={`${plan.name} plan`}>
          <h2>{plan.name}</h2>
          {plan.description && <p className="muted">{plan.description}</p>}
          <p>
            {plan.features.map((key) => {
              const f = featureName.get(key);
              return (
                <span key={key}>
                  <Badge tone={f?.available ? "good" : "warn"}>
                    {f?.name ?? key}{f && !f.available ? " (not yet available)" : ""}
                  </Badge>{" "}
                </span>
              );
            })}
          </p>
          <ActionForm action={updatePlan.bind(null, plan.key)} submitLabel={`Save ${plan.name}`}>
            <div className="form-grid">
              <Field label="Monthly price, ₦">
                <input type="number" min={0} name="monthly_price_ngn" defaultValue={plan.monthly_price_ngn ?? ""} />
              </Field>
              <Field label="Setup fee, ₦">
                <input type="number" min={0} name="setup_fee_ngn" defaultValue={plan.setup_fee_ngn ?? ""} />
              </Field>
              {Object.entries(LIMIT_LABELS).map(([key, label]) => (
                <Field key={key} label={label}>
                  <input type="number" min={0} step="any" name={`limit:${key}`} required
                    defaultValue={plan.limits[key] ?? ""} />
                </Field>
              ))}
            </div>
          </ActionForm>
        </section>
      ))}
    </>
  );
}
