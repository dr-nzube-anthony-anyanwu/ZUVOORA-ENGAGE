/**
 * Phase 4c: a patient books from the chat on the clinic's website (local fake Cal.com).
 * The confirmation is shown only after the provider confirmed the booking.
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

test("a patient books an appointment from the website chat", async ({ page }) => {
  const { tenantA, ownerA, widgetKey, clinicSite } = fx();

  // Clinic setup: connect Cal.com and offer "Eye exam".
  await signIn(page, ownerA);
  await page.goto(`/clinics/${tenantA}/scheduling`);
  await page.getByLabel("Cal.com API key").fill(KEY);
  await page.getByRole("button", { name: "Connect Cal.com" }).click();
  await page.getByLabel("Offer Eye exam").check();
  await page.getByRole("button", { name: "Save appointment types" }).click();
  await expect(page.getByText("Appointment types saved.")).toBeVisible();

  // Patient: book from the chat on the clinic's website.
  const patient = await page.context().browser()!.newContext();
  const site = await patient.newPage();
  await site.goto(`http://${clinicSite}:4180/?key=${widgetKey}`);
  await site.getByRole("button", { name: "Chat with us" }).click();
  const chat = site.frameLocator('iframe[title="Clinic chat assistant"]');
  await chat.getByRole("button", { name: "Book an appointment" }).click();
  await chat.getByRole("button", { name: "Eye exam · 30 min" }).click();
  await chat.locator(".times .choice").first().click();
  const details = chat.locator(".booking-form");
  await details.getByLabel("Full name").fill("E2E Patient");
  await details.getByLabel("Email").fill("e2e.patient@example.com");
  await details.getByRole("checkbox").check();
  await details.getByRole("button", { name: "Book this time" }).click();
  await expect(chat.getByText(/^Booked: Eye exam on /)).toBeVisible();
  await patient.close();

  // The booked time is no longer offered to the next visitor.
  const next = await page.context().browser()!.newContext();
  const other = await next.newPage();
  await other.goto(`http://${clinicSite}:4180/?key=${widgetKey}`);
  await other.getByRole("button", { name: "Chat with us" }).click();
  const chat2 = other.frameLocator('iframe[title="Clinic chat assistant"]');
  await chat2.getByRole("button", { name: "Book an appointment" }).click();
  await chat2.getByRole("button", { name: "Eye exam · 30 min" }).click();
  await expect(chat2.locator(".times .choice")).toHaveCount(5);  // 6 offered, 1 booked
  await next.close();

  // Clean up: disconnect so other tests start without booking.
  await page.goto(`/clinics/${tenantA}/scheduling`);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Disconnect" }).click();
  await expect(page.getByText("Not connected")).toBeVisible();
});
