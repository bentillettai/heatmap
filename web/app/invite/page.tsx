"use client";
import { useConvexAuth, useMutation, useQuery } from "convex/react";
import { useState } from "react";
import { api } from "../../convex/_generated/api";
import type { Id } from "../../convex/_generated/dataModel";
import SignIn from "../SignIn";

// ben's page for the invite list: who can log in, and adding someone.
export default function Invite() {
  const { isLoading, isAuthenticated } = useConvexAuth();
  if (isLoading) return <p className="hm-wait">Loading…</p>;
  return isAuthenticated ? <People /> : <SignIn />;
}

function People() {
  const people = useQuery(api.people.list);
  const invite = useMutation(api.people.invite);
  const uninvite = useMutation(api.people.uninvite);
  const [status, setStatus] = useState("");
  const [confirm, setConfirm] = useState<Id<"people"> | null>(null);

  if (people === undefined) return <p className="hm-wait">Loading…</p>;
  if (people === null) return <p className="hm-wait">Only ben can manage the invite list. <a href="/">Back to Heatmap</a></p>;

  async function add(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    setStatus("Saving…");
    try {
      await invite({ email: String(f.get("email")), name: String(f.get("name")) });
      form.reset();
      setStatus("Invited ✓. Send them the site's address; they choose \"Create your account\" with this email.");
    } catch (err) {
      setStatus(String((err as { data?: unknown }).data ?? "Couldn't save. Try again."));
    }
  }

  return (
    <main className="hm-auth">
      <div className="hm-people">
        <p><a href="/">← Back to Heatmap</a></p>
        <h1>Who can log in</h1>
        <ul>
          {people.map((p) => (
            <li key={p.id}>
              <b>{p.name}</b>{p.owner ? " (owner)" : ""} · {p.email.endsWith(".pending") ? "email not set yet" : p.email} ·{" "}
              {p.signedUp ? "has an account" : "not signed up yet"}
              {!p.owner && (
                <button
                  type="button"
                  onClick={async () => {
                    if (confirm !== p.id) return setConfirm(p.id);
                    setConfirm(null);
                    await uninvite({ id: p.id });
                  }}
                >
                  {confirm === p.id ? "Remove? Click again" : "Remove"}
                </button>
              )}
            </li>
          ))}
        </ul>
        <form onSubmit={add}>
          <h2>Invite someone</h2>
          <label>Name<input name="name" required /></label>
          <label>Email<input name="email" type="email" required /></label>
          <button type="submit">Invite</button>
          {status && <p role="status">{status}</p>}
          <p className="small">Removing someone stops their login. Their comments stay.</p>
        </form>
      </div>
    </main>
  );
}
