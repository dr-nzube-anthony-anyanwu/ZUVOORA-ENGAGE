/**
 * Design track D1–D3: the public website (homepage, accessibility statement, demo requests) and
 * the restyled sign-in page. Automated WCAG 2.2 AA checks with axe; keyboard use; small screens;
 * a demo request travels from the public form to the MFA platform console.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { totp, type E2EFixtures } from "./fixtures";

const fx = (): E2EFixtures => JSON.parse(process.env.E2E_FIXTURES ?? "null");
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  const summary = results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(summary).toEqual([]);
}

async function expectNoSidewaysScroll(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

test("homepage tells the story, is accessible and is honest about what is available", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Your clinic is caring for patients. Who's welcoming the next one?");
  await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  await expect(page.getByText("Illustrative example · sample clinic, not a live conversation").first()).toBeVisible();
  // Planned features are never shown as available.
  const roadmap = page.getByRole("region", { name: "What's coming next." });
  for (const name of ["WhatsApp", "Voice assistant", "ZUVOORA ecosystem"]) {
    await expect(roadmap.getByRole("heading", { name })).toBeVisible();
  }
  await expect(page.getByRole("row", { name: /WhatsApp/ })).toContainText("Coming soon");
  await expect(page.getByRole("row", { name: /WhatsApp/ })).not.toContainText("Included");
  await expectAccessible(page);
  await expectNoSidewaysScroll(page);
});

test("questions open from the keyboard and the scripted demo responds", async ({ page }) => {
  await page.goto("/");
  const question = page.locator("summary", { hasText: "Could it give patients incorrect medical advice?" });
  await question.focus();
  await expect(question).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Engage is designed not to give medical advice at all/)).toBeVisible();

  const demo = page.getByRole("region", { name: "See the experience your patients could have." });
  await demo.getByRole("button", { name: "My eye suddenly went dark — what should I do?" }).click();
  await expect(demo.getByText(/This sounds like it could be urgent/)).toBeVisible();
  await expect(demo.getByText(/never a diagnosis/)).toBeVisible();
});

test("small screens: no sideways scrolling, menu works, pages stay accessible", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  for (const path of ["/", "/request-demo", "/accessibility", "/login"]) {
    await page.goto(path);
    await expectNoSidewaysScroll(page);
  }
  await page.goto("/");
  await page.getByLabel("Menu").click();
  await page.getByRole("navigation", { name: "Mobile" }).getByRole("link", { name: "Plans" }).click();
  await expect(page.getByRole("heading", { name: /Start with what your clinic needs/ })).toBeInViewport();
  await expectAccessible(page);
});

test("accessibility statement and sign-in page pass automated checks", async ({ page }) => {
  await page.goto("/accessibility");
  await expect(page.getByRole("heading", { level: 1, name: "Accessibility statement" })).toBeVisible();
  await expectAccessible(page);
  await page.goto("/login");
  await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
  await expect(page.getByText("Welcome back to better patient conversations.")).toBeVisible();
  await expectAccessible(page);
});

test("a demo request reaches the platform console and nowhere else", async ({ page }) => {
  const { platformAdmin, ownerA, runId } = fx();
  const clinic = `Sample Optics ${runId}`;

  await page.goto("/");
  await page.getByRole("link", { name: "Request a demo" }).first().click();
  await expect(page).toHaveURL(/\/request-demo$/);
  await expectAccessible(page);
  await page.getByLabel("Your name").fill("Ada Example");
  await page.getByLabel("Clinic or organisation").fill(clinic);
  await page.getByLabel("Work email").fill(`ada.${runId}@example.com`);
  await page.getByLabel("City").fill("Abuja");
  await page.getByLabel("Interested in").selectOption("pilot");
  // Without consent nothing is sent (browser validation keeps the form on the page).
  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.getByRole("button", { name: "Send request" })).toBeVisible();
  await page.getByLabel(/I agree that ZubeVision/).check();
  await page.getByRole("button", { name: "Send request" }).click();
  await expect(page.getByRole("status")).toContainText("we've received your request");

  // A clinic owner cannot see requests.
  await page.goto("/login");
  await page.getByLabel("Email").fill(ownerA.email);
  await page.getByLabel("Password").fill(ownerA.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/dashboard");
  await page.goto("/platform/demo-requests");
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.context().clearCookies();

  // The MFA platform admin sees it and marks it contacted.
  await page.goto("/login");
  await page.getByLabel("Email").fill(platformAdmin.email);
  await page.getByLabel("Password").fill(platformAdmin.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/mfa");
  await page.getByLabel("Code").fill(totp(platformAdmin.totpSecret));
  await page.getByRole("button", { name: "Verify" }).click();
  await page.waitForURL("**/dashboard");
  await page.goto("/platform/demo-requests");
  const request = page.getByRole("region", { name: `Request from ${clinic}` });
  await expect(request).toContainText("Pilot programme");
  await expect(request).toContainText(`ada.${runId}@example.com`);
  await request.getByLabel("Status").selectOption("contacted");
  await request.getByRole("button", { name: "Save status" }).click();
  await expect(request.getByText("Status saved.")).toBeVisible();
});
