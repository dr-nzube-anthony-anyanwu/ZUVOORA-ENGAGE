/**
 * Shared helpers for the LOCAL demo scripts (demo-setup, demo-site). They refuse to run against
 * anything but the local Supabase stack started with `npm run db:start`. Synthetic data only.
 */
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import pg from "pg";

const here = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(here, "../../..");
export const DEMO_HOST = "lumen-eye-clinic.localhost";
export const DEMO_SITE_PORT = 4180;
export const DEMO_LEGAL_NAME = "Lumen Eye Clinic (demo) Ltd";

/** Local Supabase URLs and keys from `supabase status`; throws unless everything is local. */
export function localStack() {
  let status;
  try {
    status = JSON.parse(execFileSync(process.execPath,
      [path.join(ROOT, "node_modules", "supabase", "dist", "supabase.js"), "status", "-o", "json"],
      { cwd: ROOT, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }));
  } catch {
    throw new Error("The local database is not running. Start it first: npm run db:start");
  }
  const local = /^http:\/\/(127\.0\.0\.1|localhost):\d+$/;
  if (!local.test(status.API_URL) || !/@(127\.0\.0\.1|localhost):/.test(status.DB_URL)) {
    throw new Error("Refusing to run: the demo scripts only work with the LOCAL database.");
  }
  return status;
}

export async function withDb(stack, fn) {
  const db = new pg.Client({ connectionString: stack.DB_URL });
  await db.connect();
  try {
    return await fn(db);
  } finally {
    await db.end();
  }
}

export async function demoClinic(db) {
  const { rows } = await db.query(
    `select t.id, t.display_name, w.public_key, w.enabled from public.tenants t
       join public.widget_configs w on w.tenant_id = t.id where t.legal_name = $1`, [DEMO_LEGAL_NAME]);
  return rows[0] ?? null;
}
