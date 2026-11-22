/**
 * E2E fixtures against the LOCAL Supabase stack only. Synthetic users (@example.com) with random
 * passwords and two synthetic clinics are created before the run and removed afterwards.
 */
import { execFileSync } from "node:child_process";
import { createHmac, randomBytes, randomUUID } from "node:crypto";
import path from "node:path";
import { Client } from "pg";

export type E2EUser = { email: string; password: string; id: string };
export type E2EFixtures = {
  runId: string;
  tenantA: string;
  tenantB: string;
  ownerA: E2EUser;
  receptionistA: E2EUser;
  ownerB: E2EUser;
  /** An MFA-enrolled platform administrator (TOTP secret kept only in this test run). */
  platformAdmin: E2EUser & { totpSecret: string };
  seededFaqA: string;
  widgetKey: string;
  clinicSite: string;
  otherSite: string;
};

type Stack = { API_URL: string; DB_URL: string; SECRET_KEY: string };

const LOCAL = /^http:\/\/(127\.0\.0\.1|localhost):\d+$/;

export function localStack(): Stack {
  const fromEnv = {
    API_URL: process.env.E2E_SUPABASE_URL ?? "",
    DB_URL: process.env.E2E_SUPABASE_DB_URL ?? "",
    SECRET_KEY: process.env.E2E_SUPABASE_SECRET_KEY ?? "",
  };
  const stack = fromEnv.API_URL && fromEnv.DB_URL && fromEnv.SECRET_KEY
    ? fromEnv
    : (JSON.parse(execFileSync(process.execPath,
        [path.resolve(__dirname, "../../../node_modules/supabase/dist/supabase.js"), "status", "-o", "json"],
        { cwd: path.resolve(__dirname, "../../.."), encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
      )) as Stack);
  if (!LOCAL.test(stack.API_URL) || !/@(127\.0\.0\.1|localhost):/.test(stack.DB_URL)) {
    throw new Error("E2E tests may only run against a LOCAL Supabase stack.");
  }
  return stack;
}

async function createUser(stack: Stack, label: string, runId: string): Promise<E2EUser> {
  const email = `e2e.${label}.${runId}@example.com`;
  const password = `${randomBytes(18).toString("base64url")}aA1`;
  const response = await fetch(`${stack.API_URL}/auth/v1/admin/users`, {
    method: "POST",
    headers: { apikey: stack.SECRET_KEY, Authorization: `Bearer ${stack.SECRET_KEY}`,
               "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, email_confirm: true }),
  });
  if (!response.ok) throw new Error(`could not create E2E user (${response.status})`);
  const { id } = (await response.json()) as { id: string };
  return { email, password, id };
}

/** RFC 6238 TOTP (SHA-1, 30 s, 6 digits) from a base32 secret — for the test admin only. */
export function totp(secret: string, at: number = Date.now()): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of secret.replace(/=+$/, "").toUpperCase()) {
    bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  }
  const key = Buffer.from(bits.match(/.{8}/g)!.map((byte) => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 30_000)));
  const mac = createHmac("sha1", key).update(counter).digest();
  const offset = mac[mac.length - 1] & 0x0f;
  const code = (mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return code.toString().padStart(6, "0");
}

/** Enrol and verify a TOTP factor through Supabase Auth's API; returns the secret. */
async function enrolTotp(stack: Stack, user: E2EUser): Promise<string> {
  const auth = { apikey: stack.SECRET_KEY, "Content-Type": "application/json" };
  const session = await fetch(`${stack.API_URL}/auth/v1/token?grant_type=password`, {
    method: "POST", headers: auth, body: JSON.stringify({ email: user.email, password: user.password }),
  });
  if (!session.ok) throw new Error(`could not sign in the E2E platform admin (${session.status})`);
  const headers = { ...auth, Authorization: `Bearer ${((await session.json()) as { access_token: string }).access_token}` };
  const enrol = await fetch(`${stack.API_URL}/auth/v1/factors`, {
    method: "POST", headers, body: JSON.stringify({ factor_type: "totp", friendly_name: "e2e" }),
  });
  const { id, totp: { secret } } = (await enrol.json()) as { id: string; totp: { secret: string } };
  const challenge = (await (await fetch(`${stack.API_URL}/auth/v1/factors/${id}/challenge`,
    { method: "POST", headers })).json()) as { id: string };
  const verify = await fetch(`${stack.API_URL}/auth/v1/factors/${id}/verify`, {
    method: "POST", headers, body: JSON.stringify({ challenge_id: challenge.id, code: totp(secret) }),
  });
  if (!verify.ok) throw new Error(`could not verify the E2E TOTP factor (${verify.status})`);
  return secret;
}

export async function createFixtures(): Promise<E2EFixtures> {
  const stack = localStack();
  const runId = randomBytes(4).toString("hex");
  const [ownerA, receptionistA, ownerB, admin] = await Promise.all([
    createUser(stack, "owner-a", runId),
    createUser(stack, "reception-a", runId),
    createUser(stack, "owner-b", runId),
    createUser(stack, "platform", runId),
  ]);
  const platformAdmin = { ...admin, totpSecret: await enrolTotp(stack, admin) };
  const tenantA = randomUUID();
  const tenantB = randomUUID();
  const db = new Client({ connectionString: stack.DB_URL });
  await db.connect();
  try {
    await db.query("begin");
    await db.query(
      `insert into public.tenants (id, legal_name, display_name, status) values
         ($1, $2, $3, 'active'), ($4, $5, $6, 'active')`,
      [tenantA, `E2E Clinic A ${runId} Ltd`, `E2E Clinic A ${runId}`,
       tenantB, `E2E Clinic B ${runId} Ltd`, `E2E Clinic B ${runId}`],
    );
    await db.query("insert into public.clinic_profiles (tenant_id) values ($1), ($2)", [tenantA, tenantB]);
    // Full catalogue for the shared E2E clinics (Phase 5 plans); plan gates are tested separately.
    await db.query(
      "update public.tenant_subscriptions set plan_key = 'full_zuvoora', status = 'active' where tenant_id = any($1)",
      [[tenantA, tenantB]],
    );
    await db.query(
      `insert into public.tenant_memberships (tenant_id, user_id, role) values
         ($1, $2, 'owner'), ($1, $3, 'receptionist'), ($4, $5, 'owner')`,
      [tenantA, ownerA.id, receptionistA.id, tenantB, ownerB.id],
    );
    const faq = await db.query(
      `insert into public.faqs (tenant_id, draft) values ($1, $2) returning id`,
      [tenantA, { question: "Do you accept walk-in patients?", answer: "Yes, from 8am.",
                  category: null, sort_order: 0 }],
    );
    await db.query("update public.faqs set published = draft where id = $1", [faq.rows[0].id]);
    // Clinic A's chat widget: on, with a verified (fake) website domain.
    const clinicSite = `clinic-${runId}.engage-e2e.test`;
    await db.query(
      "insert into public.tenant_domains (tenant_id, hostname) values ($1, $2)", [tenantA, clinicSite]);
    await db.query(
      "update public.tenant_domains set verification_status = 'verified' where hostname = $1", [clinicSite]);
    const widget = await db.query(
      `update public.widget_configs set enabled = true, greeting = $2 where tenant_id = $1
       returning public_key`, [tenantA, `Hello from E2E Clinic A ${runId}`]);
    await db.query("insert into public.platform_admins (user_id, note) values ($1, 'e2e')", [platformAdmin.id]);
    await db.query("commit");
    return { runId, tenantA, tenantB, ownerA, receptionistA, ownerB, platformAdmin, seededFaqA: faq.rows[0].id,
             widgetKey: widget.rows[0].public_key, clinicSite,
             otherSite: `evil-${runId}.engage-e2e.test` };
  } catch (error) {
    await db.query("rollback");
    throw error;
  } finally {
    await db.end();
  }
}

export async function removeFixtures(fixtures: E2EFixtures): Promise<void> {
  const stack = localStack();
  const db = new Client({ connectionString: stack.DB_URL });
  await db.connect();
  let objects: string[] = [];
  try {
    const stored = await db.query(
      "select name from storage.objects where bucket_id = 'knowledge-originals' and (name like $1 or name like $2)",
      [`${fixtures.tenantA}/%`, `${fixtures.tenantB}/%`],
    );
    objects = stored.rows.map((row) => row.name as string);
    await db.query("delete from public.tenants where id = any($1)", [[fixtures.tenantA, fixtures.tenantB]]);
    await db.query("delete from public.platform_admins where user_id = $1", [fixtures.platformAdmin.id]);
  } finally {
    await db.end();
  }
  if (objects.length > 0) {  // Storage objects must be removed through the Storage API.
    await fetch(`${stack.API_URL}/storage/v1/object/knowledge-originals`, {
      method: "DELETE",
      headers: { apikey: stack.SECRET_KEY, Authorization: `Bearer ${stack.SECRET_KEY}`,
                 "Content-Type": "application/json" },
      body: JSON.stringify({ prefixes: objects }),
    });
  }
  for (const user of [fixtures.ownerA, fixtures.receptionistA, fixtures.ownerB, fixtures.platformAdmin]) {
    await fetch(`${stack.API_URL}/auth/v1/admin/users/${user.id}`, {
      method: "DELETE",
      headers: { apikey: stack.SECRET_KEY, Authorization: `Bearer ${stack.SECRET_KEY}` },
    });
  }
}
