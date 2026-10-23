"use client";
import { useAuthActions } from "@convex-dev/auth/react";
import { useState } from "react";

export default function SignIn() {
  const { signIn } = useAuthActions();
  const [flow, setFlow] = useState<"signIn" | "signUp">("signIn");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setBusy(true);
    const form = new FormData(e.currentTarget);
    form.set("flow", flow);
    try {
      await signIn("password", form);
    } catch (err) {
      const msg = String((err as { data?: unknown })?.data ?? (err as Error)?.message ?? "");
      setError(
        /invite list/.test(msg)
          ? "This email isn't on the invite list. Ask ben to add it."
          : flow === "signIn"
            ? "That email and password don't match. If this is your first visit, create your account instead."
            : "Couldn't create the account. Use at least 8 characters for the password, or sign in if you already have one.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="hm-auth">
      <form onSubmit={submit}>
        <svg width="46" height="40" viewBox="0 0 46 40" aria-hidden="true">
          <circle cx="16" cy="14" r="11" fill="#0e8aa0" fillOpacity=".45" />
          <circle cx="30" cy="14" r="11" fill="#5b4ce0" fillOpacity=".45" />
          <circle cx="23" cy="26" r="11" fill="#db2763" fillOpacity=".45" />
          <circle cx="23" cy="18" r="3" fill="currentColor" />
        </svg>
        <h1>Heatmap</h1>
        <p>Where a real problem, a thermal technology and an MTC capability overlap, and who to talk to.</p>
        <label>
          Email
          <input name="email" type="email" autoComplete="email" required />
        </label>
        <label>
          Password
          <input
            name="password"
            type="password"
            autoComplete={flow === "signIn" ? "current-password" : "new-password"}
            minLength={8}
            required
          />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "One moment…" : flow === "signIn" ? "Sign in" : "Create account"}
        </button>
        {error && <p className="err" role="alert">{error}</p>}
        <p className="switch">
          {flow === "signIn" ? "First time here? " : "Already have an account? "}
          <button type="button" onClick={() => { setFlow(flow === "signIn" ? "signUp" : "signIn"); setError(""); }}>
            {flow === "signIn" ? "Create your account" : "Sign in"}
          </button>
        </p>
        <p className="small">Invite only. Public information only: nothing confidential in comments.</p>
      </form>
    </main>
  );
}
