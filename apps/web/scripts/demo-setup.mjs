/**
 * `npm run demo:setup` — prepares a LOCAL demonstration (docs/operations/DEMO_GUIDE.md):
 *   * three demo accounts (platform admin, clinic owner, receptionist) with fresh passwords;
 *   * "Lumen Eye Clinic (sample)" on the Professional plan, active, with a published profile,
 *     branch and opening hours, services and FAQs (created through the real API);
 *   * the chat widget switched on and allowed on http://lumen-eye-clinic.localhost:4180 — a local
 *     stand-in for the clinic's website (real websites are verified through DNS instead).
 * Safe to run again: it never duplicates the clinic and only refreshes the demo passwords.
 * Requires the local database (npm run db:start) and the API (port 8073) to be running.
 */
import { randomBytes } from "node:crypto";
import { DEMO_HOST, DEMO_LEGAL_NAME, DEMO_SITE_PORT, demoClinic, localStack, withDb } from "./demo-local.mjs";

const API = process.env.ENGAGE_API_URL ?? "http://127.0.0.1:8073";
const ACCOUNTS = {
  admin: { email: "demo.admin@example.com", label: "ZubeVision platform admin" },
  owner: { email: "lumen.owner@example.com", label: "Clinic owner (Lumen Eye Clinic)" },
  reception: { email: "lumen.reception@example.com", label: "Receptionist (Lumen Eye Clinic)" },
};

const WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const HOURS = {
  weekly: WEEK.map((day) => (
    day === "sun" ? { day, closed: true, ranges: [] }
      : day === "sat" ? { day, closed: false, ranges: [{ open: "09:00", close: "13:00" }] }
        : { day, closed: false, ranges: [{ open: "08:00", close: "17:00" }] })),
  exceptions: [{ date: "2026-12-25", closed: true, ranges: [], note: "Christmas Day" }],
};
const PROFILE = {
  about: "Lumen Eye Clinic is a sample optometry practice used to demonstrate ZUVOORA Engage. We offer eye examinations, contact lens fittings and children's eye care.",
  public_phone: "+234 700 555 0199",
  public_email: "hello@lumen-eye-clinic.example.com",
  website_url: "https://lumen-eye-clinic.example.com",
  emergency_guidance: "If you have sudden loss of vision, a curtain over your vision, chemical splash or a serious eye injury, go to the nearest hospital emergency department immediately.",
};
const BRANCH = {
  name: "Lumen Eye Clinic — Victoria Island", address: "12 Sample Street, Victoria Island", city: "Lagos",
  phone: "+234 700 555 0199", timezone: "Africa/Lagos", opening_hours: HOURS,
  notes: "Free parking behind the building.",
};
const SERVICES = [
  { name: "Comprehensive eye examination", category: "Eye tests", description: "Full check of vision and eye health, including glaucoma screening.", duration_minutes: 45, price_note: "₦25,000" },
  { name: "Contact lens fitting", category: "Contact lenses", description: "Fitting, trial lenses and aftercare advice.", duration_minutes: 30, price_note: "₦15,000" },
  { name: "Children's eye test", category: "Eye tests", description: "A friendly eye test for children aged 4 and over.", duration_minutes: 30, price_note: "₦10,000" },
  { name: "Glasses and frames", category: "Optical", description: "A wide range of frames; lenses made to your prescription.", price_note: "From ₦20,000" },
];
const FAQS = [
  { question: "Do I need someone to drive me home after pupil dilation?", answer: "Yes. Dilation drops make your vision blurry and sensitive to light for about 4 hours, so please arrange for someone to drive you home and bring sunglasses." },
  { question: "Do you accept walk-in patients?", answer: "Yes, from 8am on weekdays, but booking an appointment means you will not have to wait." },
  { question: "What should I bring to my eye examination?", answer: "Your current glasses or contact lenses, a list of any medicines you take, and your HMO card if you have one." },
  { question: "Do you accept HMO plans?", answer: "We accept most major HMO plans. Please bring your HMO card and call us to confirm your plan before your visit." },
  { question: "How long does an eye examination take?", answer: "A comprehensive eye examination takes about 45 minutes." },
  { question: "Is there parking at the clinic?", answer: "Yes, there is free parking behind the building." },
];

function password() {
  return `${randomBytes(9).toString("base64url")}-Aa9`;  // ≥ 12 chars, upper, lower, digit
}

async function json(response, what) {
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`${what} failed (${response.status}). ${body.slice(0, 200)}`);
  }
  return response.status === 204 ? null : response.json();
}

async function ensureUser(stack, db, email, pass) {
  const admin = { apikey: stack.SECRET_KEY, Authorization: `Bearer ${stack.SECRET_KEY}`, "Content-Type": "application/json" };
  const existing = await db.query("select id from auth.users where email = $1", [email]);
  if (existing.rows[0]) {
    await json(await fetch(`${stack.API_URL}/auth/v1/admin/users/${existing.rows[0].id}`, {
      method: "PUT", headers: admin, body: JSON.stringify({ password: pass, email_confirm: true }),
    }), `Updating ${email}`);
    return existing.rows[0].id;
  }
  const created = await json(await fetch(`${stack.API_URL}/auth/v1/admin/users`, {
    method: "POST", headers: admin, body: JSON.stringify({ email, password: pass, email_confirm: true }),
  }), `Creating ${email}`);
  return created.id;
}

async function signIn(stack, email, pass) {
  const session = await json(await fetch(`${stack.API_URL}/auth/v1/token?grant_type=password`, {
    method: "POST", headers: { apikey: stack.PUBLISHABLE_KEY ?? stack.ANON_KEY, "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: pass }),
  }), `Signing in ${email}`);
  return session.access_token;
}

function api(token) {
  return async (method, path, body) => json(await fetch(`${API}/api/v1${path}`, {
    method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  }), `${method} ${path}`);
}

async function publishContent(call, tenant) {
  const profile = await call("GET", `/tenants/${tenant}/profile`);
  const draft = await call("PATCH", `/tenants/${tenant}/profile/draft`, { revision: profile.revision, content: PROFILE });
  await call("POST", `/tenants/${tenant}/profile/publish`, { revision: draft.revision });
  for (const [path, items] of [["branches", [BRANCH]], ["services", SERVICES], ["faqs", FAQS]]) {
    for (const content of items) {
      const item = await call("POST", `/tenants/${tenant}/${path}`, { content });
      await call("POST", `/tenants/${tenant}/${path}/${item.id}/publish`, { revision: item.revision });
    }
  }
}

async function main() {
  const stack = localStack();
  try {
    await json(await fetch(`${API}/health/ready`), "The API health check");
  } catch {
    throw new Error(`The API is not running at ${API}. Start it first (see the guide, terminal 2).`);
  }

  const passwords = Object.fromEntries(Object.keys(ACCOUNTS).map((k) => [k, password()]));
  const { tenantId, fresh } = await withDb(stack, async (db) => {
    const ids = {};
    for (const [key, account] of Object.entries(ACCOUNTS)) ids[key] = await ensureUser(stack, db, account.email, passwords[key]);
    await db.query(
      `insert into public.platform_admins (user_id, note) values ($1, 'local demo admin')
       on conflict (user_id) do update set is_active = true`, [ids.admin]);
    const existing = await demoClinic(db);
    if (existing) return { tenantId: existing.id, fresh: false };
    await db.query("begin");
    try {
      const { rows } = await db.query(
        `insert into public.tenants (legal_name, display_name, status) values ($1, $2, 'active') returning id`,
        [DEMO_LEGAL_NAME, "Lumen Eye Clinic (sample)"]);
      const id = rows[0].id;
      await db.query("insert into public.clinic_profiles (tenant_id) values ($1)", [id]);
      await db.query("update public.tenant_subscriptions set plan_key = 'professional', status = 'active', current_period_end = null where tenant_id = $1", [id]);
      await db.query(
        `insert into public.tenant_memberships (tenant_id, user_id, role) values ($1, $2, 'owner'), ($1, $3, 'receptionist')`,
        [id, ids.owner, ids.reception]);
      // Local stand-in for the clinic's website: *.localhost always points to this computer.
      await db.query("insert into public.tenant_domains (tenant_id, hostname) values ($1, $2)", [id, DEMO_HOST]);
      await db.query("update public.tenant_domains set verification_status = 'verified' where tenant_id = $1 and hostname = $2", [id, DEMO_HOST]);
      await db.query(
        "update public.widget_configs set enabled = true, greeting = $2 where tenant_id = $1",
        [id, "Hello! I'm the Lumen Eye Clinic assistant. I can help with our services, opening hours and appointments."]);
      await db.query("commit");
      return { tenantId: id, fresh: true };
    } catch (error) {
      await db.query("rollback");
      throw error;
    }
  });

  if (fresh) {
    const ownerToken = await signIn(stack, ACCOUNTS.owner.email, passwords.owner);
    await publishContent(api(ownerToken), tenantId);
  }

  const line = "-".repeat(72);
  console.log(`\n${line}\nZUVOORA Engage - local demo is ready ${fresh ? "(clinic created)" : "(clinic already existed; passwords refreshed)"}\n${line}`);
  console.log("Accounts (synthetic, local only - passwords change every time you run this):\n");
  for (const [key, account] of Object.entries(ACCOUNTS)) {
    console.log(`  ${account.label}\n    email:    ${account.email}\n    password: ${passwords[key]}\n`);
  }
  console.log(`Sign in:             http://localhost:3073/login`);
  console.log(`Clinic dashboard:    http://localhost:3073/clinics/${tenantId}`);
  console.log(`Demo clinic website: http://${DEMO_HOST}:${DEMO_SITE_PORT}  (start it with: npm run demo:site)`);
  console.log(`\nThe platform admin must set up two-factor authentication at first sign-in (authenticator app).`);
  console.log(`Full walkthrough: docs/operations/DEMO_GUIDE.md\n${line}\n`);
}

main().catch((error) => {
  console.error(`\nDemo setup stopped: ${error.message}\n`);
  process.exit(1);
});
