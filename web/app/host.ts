// Gives the page script (site/template.html) what the Claude page gave it:
// window.claude.use("db") and use("user"), backed by Convex instead.
import type { ConvexReactClient } from "convex/react";
import { api } from "../convex/_generated/api";

type Collection = "feedback" | "runfeedback" | "comments" | "notes";
type Snap = { docs: { id: string; data: () => unknown }[] };

export function installHost(client: ConvexReactClient, signOut: () => void) {
  const db = {
    collection(name: Collection) {
      return {
        doc(id: string) {
          return {
            set: (data: unknown) => client.mutation(api.db.set, { collection: name, id, data }),
            delete: () => client.mutation(api.db.remove, { collection: name, id }),
          };
        },
        add: async (data: unknown) => ({ id: await client.mutation(api.db.add, { collection: name, data }) }),
        onSnapshot(next: (s: Snap) => void, fail?: (e: unknown) => void) {
          const watch = client.watchQuery(api.db.list, { collection: name });
          const emit = () => {
            try {
              const rows = watch.localQueryResult();
              if (rows) next({ docs: rows.map((r) => ({ id: r.id, data: () => r.data })) });
            } catch (e) {
              fail?.(e);
            }
          };
          const stop = watch.onUpdate(emit);
          emit();
          return stop;
        },
      };
    },
  };
  const user = {
    me: () => client.query(api.people.me, {}),
    can: async () => true,
    profiles: (ids: string[]) => client.query(api.people.profiles, { ids }),
  };
  const w = window as unknown as Record<string, unknown>;
  w.claude = { use: async (what: string) => (what === "db" ? db : what === "user" ? user : null) };
  w.heatmapHost = {
    snapshot: async (runId: string) => {
      const json = await client.query(api.report.snapshot, { runId });
      if (!json) throw new Error("no snapshot");
      return JSON.parse(json);
    },
    signOut,
    invite: "/invite",
  };
}
