/**
 * Design track D4: the restyled staff dashboard and the chat widget pass automated WCAG 2.2 AA
 * checks (axe) and keep the current section marked for assistive technology.
 */
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import type { E2EFixtures } from "./fixtures";

const fx = (): E2EFixtures => JSON.parse(process.env.E2E_FIXTURES ?? "null");
const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function expectAccessible(page: Page, include?: string) {
  let builder = new AxeBuilder({ page }).withTags(WCAG);
  if (include) builder = builder.include(include);
  const results = await builder.analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

test("dashboard pages are accessible and mark the current section", async ({ page }) => {
  const { ownerA, tenantA } = fx();
  await page.goto("/login");
  await page.getByLabel("Email").fill(ownerA.email);
  await page.getByLabel("Password").fill(ownerA.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/dashboard");
  await expectAccessible(page);

  for (const [path, section] of [["", "Overview"], ["/inbox", "Inbox"], ["/services", "Services"], ["/plan", "Plan & usage"]]) {
    await page.goto(`/clinics/${tenantA}${path}`);
    const nav = page.getByRole("navigation", { name: "Clinic sections" });
    await expect(nav.getByRole("link", { name: section, exact: true })).toHaveAttribute("aria-current", "page");
    await expect(nav.locator('[aria-current="page"]')).toHaveCount(1);
    await expectAccessible(page);
  }

  // Phones: the section links become one scrollable row and the page does not scroll sideways.
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto(`/clinics/${tenantA}`);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await expect(page.getByRole("heading", { level: 1 })).toBeInViewport();
});

test("the chat widget is accessible", async ({ page }) => {
  const { widgetKey, clinicSite } = fx();
  await page.goto(`http://${clinicSite}:4180/?key=${widgetKey}`);
  await page.getByRole("button", { name: "Chat with us" }).click();
  const frame = page.frameLocator('iframe[title="Clinic chat assistant"]');
  await expect(frame.getByLabel("Your message")).toBeVisible();
  await expectAccessible(page, 'iframe[title="Clinic chat assistant"]');
});
