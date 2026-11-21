import { defineConfig, devices } from "@playwright/test";
import { randomBytes } from "node:crypto";
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
  projects: [{
    name: "chromium",
    use: {
      ...devices["Desktop Chrome"],
      // Two fake "clinic websites" on this machine, for real cross-site widget embedding.
      launchOptions: { args: ["--host-resolver-rules=MAP *.engage-e2e.test 127.0.0.1"] },
    },
  }],
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port 8073`,
      cwd: apiDir,
      env: {
        // http:// test sites may embed the widget (never allowed in staging/production).
        WIDGET_ALLOW_HTTP_FRAMES: "true",
        WIDGET_TOKEN_SECRET: process.env.WIDGET_TOKEN_SECRET ?? randomBytes(48).toString("base64url"),
      },
      url: "http://127.0.0.1:8073/health/ready",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "node e2e/site-server.mjs",
      url: "http://127.0.0.1:4180/?key=" + "0".repeat(32),
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: "npm run start",
      url: "http://localhost:3073/login",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
