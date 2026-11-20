"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const supabase = createClient();
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? ""),
    });
    if (signInError) {
      // Generic message: do not reveal whether the email exists.
      setError("Sign-in failed. Check your email and password.");
      setBusy(false);
      return;
    }
    const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    router.replace(aal?.nextLevel === "aal2" && aal.currentLevel !== "aal2" ? "/mfa" : "/dashboard");
    router.refresh();
  }

  return (
    <main className="narrow">
      <div className="brand">ZUBEVISION TECHNOLOGIES LTD.</div>
      <h1>Sign in</h1>
      <section className="panel">
        <form onSubmit={onSubmit} className="form">
          <label>
            Email
            <input name="email" type="email" autoComplete="email" required maxLength={254} />
          </label>
          <label>
            Password
            <input name="password" type="password" autoComplete="current-password" required minLength={12} />
          </label>
          {error && <p role="alert" className="error">{error}</p>}
          <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <p className="hint">Accounts are created by invitation from your clinic or ZubeVision.</p>
      </section>
    </main>
  );
}
