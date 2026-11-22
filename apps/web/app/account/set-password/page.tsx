"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { AuthShell } from "@/components/AuthShell";
import { createClient } from "@/lib/supabase/client";

export default function SetPasswordPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    if (password !== String(form.get("confirm") ?? "")) {
      setError("The passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    const { error: updateError } = await createClient().auth.updateUser({ password });
    if (updateError) {
      setError("Password not accepted. Use at least 12 characters with upper- and lower-case letters and a number.");
      setBusy(false);
      return;
    }
    router.replace("/dashboard");
    router.refresh();
  }

  return (
    <AuthShell
      title="Set your password"
      intro="Use at least 12 characters, with upper- and lower-case letters and a number."
      asideTitle="Welcome to ZUVOORA Engage."
      asideText="You've been invited to your clinic's workspace. Set a password to get started."
    >
      <form onSubmit={onSubmit} className="form">
        <label>
          New password
          <input name="password" type="password" autoComplete="new-password" required minLength={12} />
        </label>
        <label>
          Confirm password
          <input name="confirm" type="password" autoComplete="new-password" required minLength={12} />
        </label>
        {error && <p role="alert" className="error">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? "Saving…" : "Save password"}</button>
      </form>
    </AuthShell>
  );
}
