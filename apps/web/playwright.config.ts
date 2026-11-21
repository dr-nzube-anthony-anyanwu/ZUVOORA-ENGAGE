import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

/**
 * End-to-end tests: real browser -> dashboard (production build) -> Engage API -> LOCAL Supabase.
 * Prerequisites: `npm run db:start` (repo root), `npm run build` (this app), API dependencies
 * installed. Run with `npm run test:e2e`.
 */
const apiDir = path.resolve(__dirname, "../api");
const python = process.env.E2E_PYTHON
  ?? (process.platform === "win32" ? path.join(apiDir, ".venv", "Scripts", "python.exe")
                                   : path.join(apiDir, ".venv", "bin", "python"));

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: "http://localhost:3073",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8073`,
      cwd: apiDir,
      url: "http://127.0.0.1:8073/health/ready",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npm run start",
      url: "http://localhost:3073/login",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
