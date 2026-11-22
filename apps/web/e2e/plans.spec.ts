/**
 * Phase 5a: an MFA platform admin changes a clinic's plan; clinic owners see their plan, what is
 * included and what is "not yet available"; receptionists do not see billing.
 */
import { expect, test, type Page } from "@playwright/test";
import { totp, type E2EFixtures } from "./fixtures";

const fx = (): E2EFixtures => JSON.parse(process.env.E2E_FIXTURES ?? "null");

async function signIn(page: Page, user: { email: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/dashboard");
}

test("platform admin changes a clinic's plan and the clinic sees it", async ({ page }) => {
  const { platformAdmin, tenantA, tenantB, ownerA, ownerB, receptionistA, runId } = fx();

  // Platform admin: sign in (an enrolled factor sends them to /mfa), verify, change Clinic B's plan.
  await page.goto("/login");
  await page.getByLabel("Email").fill(platformAdmin.email);
  await page.getByLabel("Password").fill(platformAdmin.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/mfa");
  await page.getByLabel("Code").fill(totp(platformAdmin.totpSecret));
  await page.getByRole("button", { name: "Verify" }).click();
  await page.waitForURL("**/dashboard");
  await page.getByRole("link", { name: "Open platform tools" }).click();
  const clinicB = page.getByRole("region", { name: `E2E Clinic B ${runId}` });
  await expect(clinicB).toContainText("Full ZUVOORA");
  await clinicB.getByLabel("Plan").selectOption("essentials");
  await clinicB.getByRole("button", { name: "Save subscription" }).click();
  await expect(clinicB.getByText(/Subscription updated/)).toBeVisible();
  await page.goto("/platform/plans");
  await expect(page.getByRole("region", { name: "Premium plan" })).toContainText("Voice AI (not yet available)");
  await page.context().clearCookies();

  // Clinic B's owner sees Essentials: booking included, reminders not.
  await signIn(page, ownerB);
  await page.goto(`/clinics/${tenantB}/plan`);
  await expect(page.getByRole("heading", { name: "Essentials" })).toBeVisible();
  await expect(page.getByRole("row", { name: /Online booking/ })).toContainText("Included");
  await expect(page.getByRole("row", { name: /Appointment reminders/ })).toContainText("Not in this plan");
  await expect(page.getByRole("row", { name: /Website domains/ })).toContainText("1");
  await page.context().clearCookies();

  // Clinic A's owner (Full ZUVOORA) sees unbuilt features as "not yet available".
  await signIn(page, ownerA);
  await page.goto(`/clinics/${tenantA}/plan`);
  await expect(page.getByRole("row", { name: /WhatsApp/ })).toContainText("Included — not yet available");
  await page.context().clearCookies();

  // Receptionists do not see the plan.
  await signIn(page, receptionistA);
  await page.goto(`/clinics/${tenantA}`);
  await expect(page.getByRole("link", { name: "Plan & usage" })).toHaveCount(0);
});
