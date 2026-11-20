import type { EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";
import { safeNextPath } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

const ALLOWED_TYPES: ReadonlySet<EmailOtpType> = new Set(["invite", "recovery", "email_change"]);

/** Exchanges a one-time email token (invite / password recovery) for a session, server-side. */
export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const next = safeNextPath(searchParams.get("next"), "/account/set-password");

  const failure = new URL("/login", request.url);
  if (!tokenHash || !type || !ALLOWED_TYPES.has(type)) {
    return NextResponse.redirect(failure);
  }
  const supabase = await createClient();
  const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
  return NextResponse.redirect(error ? failure : new URL(next, request.url));
}
