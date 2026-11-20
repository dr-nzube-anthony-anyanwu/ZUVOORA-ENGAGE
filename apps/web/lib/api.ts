import { createClient } from "@/lib/supabase/server";

/** Server-side only. The API base URL is not a public value and is never sent to the browser. */
const API_BASE_URL = process.env.ENGAGE_API_URL ?? "http://127.0.0.1:8073";

export type Membership = {
  tenant_id: string;
  role: "owner" | "admin" | "receptionist" | "viewer";
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
  ) {
    super(`API request failed: ${status} ${code}`);
  }
}

/** Call the Engage API as the signed-in user. The API re-verifies the token and enforces RLS. */
export async function apiGet<T>(path: string): Promise<T> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new ApiRequestError(401, "unauthenticated");

  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiRequestError(response.status, body?.error?.code ?? "unknown_error");
  }
  return (await response.json()) as T;
}
