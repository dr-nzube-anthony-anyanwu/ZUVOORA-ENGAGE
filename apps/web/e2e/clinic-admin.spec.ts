/**
 * Phase 2 acceptance: a synthetic clinic configures and publishes its content through the
 * dashboard; another clinic can neither view nor edit it; read-only staff cannot change it.
 */
import { expect, test, type Page } from "@playwright/test";
import type { E2EFixtures, E2EUser } from "./fixtures";

const fx = (): E2EFixtures => JSON.parse(process.env.E2E_FIXTURES ?? "null");

async function signIn(page: Page, user: E2EUser) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/dashboard");
}

/** Click a section in the clinic sidebar. */
async function openSection(page: Page, name: string) {
  await page.getByRole("navigation", { name: "Clinic sections" })
    .getByRole("link", { name, exact: true }).click();
}

async function expectNotFound(page: Page, url: string) {
  const response = await page.goto(url);
  expect(response?.status()).toBe(404);
  await expect(page.getByText("This page could not be found")).toBeVisible();
}

test("anonymous visitors are sent to the login page", async ({ page }) => {
  await page.goto(`/clinics/${fx().tenantA}`);
  await expect(page).toHaveURL(/\/login$/);
});

test("owner configures and publishes clinic content", async ({ page }) => {
  const { ownerA, runId } = fx();
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  const dialogs: string[] = [];
  page.on("dialog", async (dialog) => {
    dialogs.push(dialog.message());
    await dialog.accept();  // confirmation prompts for destructive actions
  });
  await signIn(page, ownerA);
  await page.getByRole("link", { name: `E2E Clinic A ${runId}` }).click();
  await expect(page.getByRole("heading", { name: /Setup checklist · 1 of 6/ })).toBeVisible();

  // Clinic profile: save a draft, then publish it.
  await openSection(page, "Clinic profile");
  await page.getByLabel("About the clinic").fill("Family eye clinic in Lekki.");
  await page.getByLabel("Public phone").fill("+234 801 000 0000");
  await page.getByLabel("Eye emergency guidance")
    .fill("For sudden vision loss or an eye injury, go to the nearest emergency department now.");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByText("Draft saved.")).toBeVisible();
  await page.getByRole("button", { name: /Publish revision/ }).click();
  await expect(page.getByText("Live", { exact: true })).toBeVisible();

  // Service.
  await openSection(page, "Services");
  await page.getByLabel("Service name").fill("Comprehensive eye examination");
  await page.getByLabel("Typical duration (minutes)").fill("45");
  await page.getByLabel("Price information").fill("From NGN 15,000");
  await page.getByRole("button", { name: "Create draft" }).click();
  await page.waitForURL(/\/services\/[0-9a-f-]{36}/);
  await page.getByRole("button", { name: /Publish revision 1/ }).click();
  await expect(page.getByText("Live", { exact: true })).toBeVisible();

  // FAQ containing markup: must be shown as text and never executed.
  await openSection(page, "FAQs");
  await page.getByLabel("Question", { exact: true }).fill("What should I bring to my appointment?");
  await page.getByLabel("Answer", { exact: true })
    .fill('<img src=x onerror="window.__xss=1"><script>window.__xss=1</script> Bring a photo ID.');
  await page.getByRole("button", { name: "Create draft" }).click();
  await page.waitForURL(/\/faqs\/[0-9a-f-]{36}/);
  await page.getByRole("button", { name: /Publish revision 1/ }).click();
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Answer", { exact: true })).toHaveValue(/<script>window.__xss=1<\/script>/);
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();

  // Branch with structured opening hours and a holiday.
  await openSection(page, "Branches & hours");
  await page.getByLabel("Branch name").fill("Lekki");
  await page.getByLabel("City", { exact: true }).fill("Lagos");
  await page.getByRole("button", { name: "Create draft" }).click();
  await page.waitForURL(/\/branches\/[0-9a-f-]{36}/);
  await page.getByLabel("Publish opening hours for this branch").check();
  await page.getByLabel("Saturday closed").uncheck();
  await page.getByLabel("Saturday opens (1)").fill("09:00");
  await page.getByLabel("Saturday closes (1)").fill("13:00");
  await page.getByLabel("Special day 1 date").fill("2026-12-25");
  await page.getByLabel("Special day 1 note").fill("Christmas Day");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByText("Draft saved.")).toBeVisible();
  await page.getByRole("button", { name: /Publish revision 2/ }).click();
  await expect(page.getByText("Live", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Saturday opens (1)")).toHaveValue("09:00");

  // Invalid hours are refused with a readable message and nothing changes.
  await page.getByLabel("Monday opens (1)").fill("18:00");
  await page.getByLabel("Monday closes (1)").fill("08:00");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.locator("form [role=alert]")).toContainText("close must be after open");

  // Knowledge document: upload, review the extracted text, approve and publish.
  await openSection(page, "Documents");
  await page.getByLabel("Title", { exact: true }).fill("Payment policy");
  await page.getByLabel("File", { exact: true }).setInputFiles({
    name: "payment-policy.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# Payment\n\nWe accept cash, transfers and most HMO plans."),
  });
  await page.getByRole("button", { name: "Upload" }).click();
  await page.waitForURL(/\/documents\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Awaiting review").first()).toBeVisible();
  await page.getByRole("link", { name: "Review" }).click();
  await expect(page.getByLabel("Extracted text")).toContainText("most HMO plans");
  await page.getByRole("button", { name: "Approve and publish" }).click();
  await page.waitForURL(/\/documents\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Version 1 is live")).toBeVisible();

  // A disguised executable is refused with a clear message.
  await page.getByLabel("File", { exact: true }).setInputFiles({
    name: "update.pdf", mimeType: "application/pdf", buffer: Buffer.from("MZ\x90\x00 not a pdf"),
  });
  await page.getByRole("button", { name: "Upload version" }).click();
  await expect(page.locator("form [role=alert]")).toContainText(/PDF, Word|do not match/);

  // Website domain: registration shows the exact DNS record to publish.
  await openSection(page, "Website domains");
  await page.getByLabel("Website host name").fill(`www.e2e-${runId}.example.com`);
  await page.getByRole("button", { name: "Add domain" }).click();
  await expect(page.getByText(`_zuvoora-engage.www.e2e-${runId}.example.com`)).toBeVisible();
  await expect(page.getByText(/^zuvoora-engage-verification=[0-9a-f]{64}$/)).toBeVisible();

  // Everything except domain verification is now complete.
  await openSection(page, "Overview");
  await expect(page.getByRole("heading", { name: /Setup checklist · 5 of 6/ })).toBeVisible();
  expect(dialogs).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test("another clinic cannot view or edit Clinic A", async ({ page }) => {
  const { tenantA, tenantB, ownerB, seededFaqA, runId } = fx();
  await signIn(page, ownerB);
  await expect(page.getByRole("link", { name: `E2E Clinic A ${runId}` })).toHaveCount(0);
  for (const url of [
    `/clinics/${tenantA}`,
    `/clinics/${tenantA}/faqs`,
    `/clinics/${tenantA}/faqs/${seededFaqA}`,
    `/clinics/${tenantA}/documents`,
    `/clinics/${tenantA}/team`,
    `/clinics/${tenantB}/faqs/${seededFaqA}`,  // own clinic in the URL, A's item id
    `/clinics/not-a-uuid`,
    `/clinics/${tenantB}/faqs/..%2F..%2Fplatform%2Ftenants`,
  ]) {
    await expectNotFound(page, url);
  }
  // Clinic B's own workspace still works.
  await page.goto(`/clinics/${tenantB}`);
  await expect(page.getByRole("heading", { name: `E2E Clinic B ${runId}` })).toBeVisible();
});

test("receptionist has read-only access", async ({ page }) => {
  const { tenantA, receptionistA, seededFaqA } = fx();
  await signIn(page, receptionistA);
  await page.goto(`/clinics/${tenantA}/faqs/${seededFaqA}`);
  await expect(page.getByLabel("Question", { exact: true })).toHaveValue("Do you accept walk-in patients?");
  await expect(page.getByLabel("Question", { exact: true })).toBeDisabled();
  await expect(page.getByText("You have read-only access.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Publish|Archive|Unpublish/ })).toHaveCount(0);
  await page.goto(`/clinics/${tenantA}/faqs`);
  await expect(page.getByRole("button", { name: "Create draft" })).toHaveCount(0);
  await page.goto(`/clinics/${tenantA}/team`);
  await expect(page.getByText("Only owners and admins can view and manage the team.")).toBeVisible();
});
