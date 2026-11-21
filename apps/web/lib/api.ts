import "server-only";

import { createClient } from "@/lib/supabase/server";

/** Server-side only. The API base URL is not a public value and is never sent to the browser. */
const API_BASE_URL = process.env.ENGAGE_API_URL ?? "http://127.0.0.1:8073";

export type Role = "owner" | "admin" | "receptionist" | "viewer";

export type Membership = {
  tenant_id: string;
  role: Role;
  membership_active: boolean;
  tenant_display_name: string | null;
  tenant_status: "pending" | "active" | "suspended" | "closed" | null;
  accessible: boolean;
};

export type Me = {
  user_id: string;
  email: string | null;
  mfa_verified: boolean;
  is_platform_admin: boolean;
  memberships: Membership[];
};

export class ApiRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    /** User-safe message written by the API (never contains submitted values). */
    public readonly userMessage: string,
    public readonly details: string[] = [],
  ) {
    super(`API request failed: ${status} ${code}`);
  }
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** True for a canonical UUID. Every id placed in an API path must pass this check. */
export function isUuid(value: unknown): value is string {
  return typeof value === "string" && UUID.test(value);
}

/** Build an API path from fixed segments and validated ids (prevents path manipulation). */
export function tenantPath(tenantId: string, ...segments: string[]): string {
  if (!isUuid(tenantId)) throw new ApiRequestError(404, "not_found", "Not found.");
  for (const segment of segments) {
    if (!/^[a-z0-9_-]+$/i.test(segment)) {
      throw new ApiRequestError(404, "not_found", "Not found.");
    }
  }
  return ["/api/v1/tenants", tenantId, ...segments].join("/");
}

function readableDetail(detail: { loc?: string[]; msg?: string }): string {
  const field = (detail.loc ?? [])
    .filter((part) => !["body", "content"].includes(part) && !/^\d+$/.test(part))
    .map((part) => part.replace(/_/g, " "))
    .pop();
  const message = (detail.msg ?? "Invalid value").replace(/^Value error, /, "");
  return field ? `${field}: ${message}` : message;
}

/** Call the Engage API as the signed-in user. The API re-verifies the token and enforces RLS. */
export async function apiFetch<T>(
  path: string,
  init: { method?: string; json?: unknown; form?: FormData } = {},
): Promise<T> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ApiRequestError(401, "unauthenticated", "Please sign in again.");

  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  let body: BodyInit | undefined;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  } else if (init.form) {
    body = init.form;
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: init.method ?? "GET",
      headers,
      body,
      cache: "no-store",
    });
  } catch {
    throw new ApiRequestError(503, "api_unreachable", "The Engage service is unavailable.");
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const error = payload?.error ?? {};
    throw new ApiRequestError(
      response.status,
      error.code ?? "unknown_error",
      typeof error.message === "string" ? error.message : "The request could not be completed.",
      Array.isArray(error.details) ? error.details.map(readableDetail) : [],
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return apiFetch<T>(path);
}
