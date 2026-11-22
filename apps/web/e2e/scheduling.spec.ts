/**
 * Phase 4b: an owner connects Cal.com (a local fake), chooses appointment types and disconnects;
 * a receptionist sees the setup read-only. The API key never appears on any page.
 */
import { expect, test, type Page } from "@playwright/test";
import type { E2EFixtures } from "./fixtures";

const fx = (): E2EFixtures => JSON.parse(process.env.E2E_FIXTURES ?? "null");
const KEY = "cal_e2e_test_key_0000000001";

async function signIn(page: Page, user: { email: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/dashboard");
}

test("owner connects Cal.com and chooses what patients can book", async ({ page }) => {
  const { tenantA, ownerA, receptionistA } = fx();
  await signIn(page, ownerA);
  await page.goto(`/clinics/${tenantA}/scheduling`);
  await expect(page.getByText("Not connected")).toBeVisible();

  await page.getByLabel("API key").fill("cal_wrong_key_123456789");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "did not accept" })).toBeVisible();

  await page.getByLabel("API key").fill(KEY);
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByText("Connected", { exact: true })).toBeVisible();
  await expect(page.getByText("e2e-clinic")).toBeVisible();
  await expect(page.locator("body")).not.toContainText(KEY);
  await expect(page.locator("body")).toContainText(`…${KEY.slice(-4)}`);

  await page.getByLabel("Offer Eye exam").check();
  await page.getByLabel("Name patients see for Eye exam").fill("Comprehensive eye exam");
  await page.getByRole("button", { name: "Save appointment types" }).click();
  await expect(page.getByText("Appointment types saved.")).toBeVisible();
  await expect(page.getByLabel("Offer Eye exam")).toBeChecked();
  await expect(page.getByLabel("Offer Lens fitting")).not.toBeChecked();
  await expect(page.getByText("You confirm each booking in Cal.com.")).toBeVisible();
  await page.context().clearCookies();

  await signIn(page, receptionistA);
  await page.goto(`/clinics/${tenantA}/scheduling`);
  await expect(page.getByRole("listitem").filter({ hasText: "Comprehensive eye exam · 30 min" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Disconnect" })).toHaveCount(0);
  await page.context().clearCookies();

  await signIn(page, ownerA);
  await page.goto(`/clinics/${tenantA}/scheduling`);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Disconnect" }).click();
  await expect(page.getByText("Not connected")).toBeVisible();
});
