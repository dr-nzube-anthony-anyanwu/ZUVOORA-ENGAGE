/**
 * Phase 3g: a clinic owner uploads a photo of a price list; it is read by AI (a local fake
 * OpenRouter), flagged "Read by AI", reviewed and approved. Receptionists cannot upload.
 */
import { expect, test, type Page } from "@playwright/test";
import type { E2EFixtures, E2EUser } from "./fixtures";

const fx = (): E2EFixtures => JSON.parse(process.env.E2E_FIXTURES ?? "null");

// A valid blank 64×32 PNG made with Pillow (synthetic; the fake model returns a fixed transcription).
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAEAAAAAgCAIAAAAt/+nTAAAANUlEQVR42u3PAQkAAAgDMLV/59tCELYG6yT12dRzAgICAgICAgIC" +
  "AgICAgICAgICAgICAvcWMisDPdIJjMIAAAAASUVORK5CYII=",
  "base64",
);

async function signIn(page: Page, user: E2EUser) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(user.email);
  await page.getByLabel("Password").fill(user.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/dashboard");
}

test("owner uploads a photo of a price list; AI reads it; owner reviews and approves", async ({ page }) => {
  const { ownerA, tenantA } = fx();
  await signIn(page, ownerA);
  await page.goto(`/clinics/${tenantA}/documents`);
  await expect(page.getByText(/never upload anything containing patient information/)).toBeVisible();
  await page.getByLabel("Title", { exact: true }).fill("Price list photo");
  await page.getByLabel("File", { exact: true }).setInputFiles({
    name: "price-list.png", mimeType: "image/png", buffer: PNG,
  });
  await page.getByRole("button", { name: "Upload" }).click();
  await page.waitForURL(/\/documents\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Read by AI", { exact: true })).toBeVisible();
  await expect(page.getByText(/Photo ·/)).toBeVisible();
  await page.getByRole("link", { name: "Review" }).click();
  await expect(page.getByRole("note")).toContainText("compare every line with the original");
  await expect(page.getByLabel("Extracted text")).toContainText("Comprehensive eye exam | 25,000");
  await page.getByRole("button", { name: "Approve and publish" }).click();
  await page.waitForURL(/\/documents\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Version 1 is live")).toBeVisible();
});

test("an unsupported image format is refused with a clear message", async ({ page }) => {
  const { ownerA, tenantA } = fx();
  await signIn(page, ownerA);
  await page.goto(`/clinics/${tenantA}/documents`);
  await page.getByLabel("Title", { exact: true }).fill("Logo");
  await page.getByLabel("File", { exact: true }).setInputFiles({
    name: "logo.svg", mimeType: "image/svg+xml", buffer: Buffer.from("<svg xmlns='http://www.w3.org/2000/svg'/>"),
  });
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page.locator("form [role=alert]")).toContainText("image (.png, .jpg, .webp)");
});
