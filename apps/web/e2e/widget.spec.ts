/**
 * Phase 3b acceptance: the widget works only on the clinic's verified website; the browser itself
 * refuses to show it elsewhere (frame-ancestors). Messages are shown as text; handover works.
 */
import { expect, test } from "@playwright/test";
import type { E2EFixtures } from "./fixtures";

const fx = (): E2EFixtures => JSON.parse(process.env.E2E_FIXTURES ?? "null");

test("widget chat and handover work on the verified clinic website", async ({ page }) => {
  const { widgetKey, clinicSite, runId } = fx();
  await page.goto(`http://${clinicSite}:4180/?key=${widgetKey}`);
  await page.getByRole("button", { name: "Chat with us" }).click();
  const chat = page.frameLocator('iframe[title="Clinic chat assistant"]');
  await expect(chat.getByText(`Hello from E2E Clinic A ${runId}`)).toBeVisible();

  await chat.getByLabel("Your message").fill('<img src=x onerror="parent.__xss=1"> Are you open on Saturday?');
  await chat.getByRole("button", { name: "Send", exact: true }).click();
  await expect(chat.getByText(/<img src=x onerror=/)).toBeVisible();  // shown as text
  await expect(chat.getByText(/can't answer questions yet/)).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined();

  await chat.getByLabel("Phone").fill("+234 801 000 0000");
  await chat.getByRole("checkbox").check();
  await chat.getByRole("button", { name: "Send my details" }).click();
  await expect(chat.getByText(/clinic team has your details/)).toBeVisible();
});

test("the browser refuses to show the widget on an unverified website", async ({ page }) => {
  const { widgetKey, otherSite, runId } = fx();
  const blocked: string[] = [];
  page.on("console", (message) => {
    if (/frame-ancestors|Refused to frame/i.test(message.text())) blocked.push(message.text());
  });
  await page.goto(`http://${otherSite}:4180/?key=${widgetKey}`);
  await page.getByRole("button", { name: "Chat with us" }).click();
  await expect.poll(() => blocked.length).toBeGreaterThan(0);
  const chat = page.frameLocator('iframe[title="Clinic chat assistant"]');
  await expect(chat.getByText(`Hello from E2E Clinic A ${runId}`)).toHaveCount(0);
});

test("owner sees the embed snippet; receptionist cannot change the widget", async ({ page }) => {
  const { tenantA, ownerA, receptionistA, widgetKey } = fx();
  for (const [user, editable] of [[ownerA, true], [receptionistA, false]] as const) {
    await page.goto("/login");
    await page.getByLabel("Email").fill(user.email);
    await page.getByLabel("Password").fill(user.password);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL("**/dashboard");
    await page.goto(`/clinics/${tenantA}/widget`);
    await expect(page.getByLabel("Embed snippet")).toContainText(`data-engage-key="${widgetKey}"`);
    await expect(page.getByRole("button", { name: "Turn chat off" })).toHaveCount(editable ? 1 : 0);
    await page.context().clearCookies();
  }
});
