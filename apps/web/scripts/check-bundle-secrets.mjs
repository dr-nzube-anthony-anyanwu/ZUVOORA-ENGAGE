#!/usr/bin/env node
/**
 * Fails the build if server-only secrets appear in browser-delivered files (.next/static).
 * Phase 1 gate: "Service-role secrets never appear in browser bundles."
 *
 * Checks (1) known secret formats and server-only variable names, and (2) the exact values of
 * any server-only secrets present in the build environment (never printed, only reported).
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("..", import.meta.url));
const STATIC_DIR = join(ROOT, ".next", "static");

const PATTERNS = [
  { name: "Supabase secret key", re: /sb_secret_[A-Za-z0-9_-]{10,}/ },
  { name: "Supabase service_role JWT claim", re: /"role"\s*:\s*"service_role"/ },
  { name: "Server-only env var name", re: /\b(SUPABASE_SECRET_KEY|SUPABASE_SERVICE_ROLE_KEY|DATABASE_URL|OPENROUTER_API_KEY|RESEND_API_KEY|APP_SIGNING_SECRET|SUPABASE_JWT_LEGACY_SECRET)\b/ },
  { name: "Postgres connection string", re: /postgres(ql)?:\/\/[^\s"'`]+:[^\s"'`]+@/ },
  { name: "Private key block", re: /-----BEGIN [A-Z ]*PRIVATE KEY-----/ },
  { name: "OpenRouter key", re: /sk-or-[A-Za-z0-9-]{20,}/ },
  { name: "Resend key", re: /\bre_[A-Za-z0-9]{20,}/ },
];

const SECRET_ENV_NAMES = [
  "SUPABASE_SECRET_KEY",
  "SUPABASE_SERVICE_ROLE_KEY",
  "DATABASE_URL",
  "OPENROUTER_API_KEY",
  "RESEND_API_KEY",
  "APP_SIGNING_SECRET",
  "SUPABASE_JWT_LEGACY_SECRET",
];
const secretValues = SECRET_ENV_NAMES.map((n) => [n, process.env[n]])
  .filter(([, v]) => typeof v === "string" && v.length >= 12);

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) yield* walk(full);
    else if (/\.(js|mjs|css|json|html|map|txt)$/.test(entry)) yield full;
  }
}

let files;
try {
  files = [...walk(STATIC_DIR)];
} catch {
  console.error(`check-bundle-secrets: ${STATIC_DIR} not found. Run "npm run build" first.`);
  process.exit(2);
}

const findings = [];
for (const file of files) {
  const text = readFileSync(file, "utf8");
  for (const { name, re } of PATTERNS) {
    if (re.test(text)) findings.push(`${relative(ROOT, file)}: ${name}`);
  }
  for (const [envName, value] of secretValues) {
    if (text.includes(value)) findings.push(`${relative(ROOT, file)}: value of ${envName}`);
  }
}

if (findings.length) {
  console.error("check-bundle-secrets: FAILED — server-only secrets found in browser files:");
  for (const f of findings) console.error(`  - ${f}`);
  process.exit(1);
}
console.log(
  `check-bundle-secrets: OK — scanned ${files.length} browser files, ` +
    `${PATTERNS.length} patterns, ${secretValues.length} secret values from the environment.`,
);
