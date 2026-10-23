// Called by the daily run (tools/convex_sync.py) with the deploy key, never
// by the page. The pipeline stays independent of Convex: it builds the report
// as before and pushes it here, and pulls what people wrote.
import { v } from "convex/values";
import { internalMutation, internalQuery } from "./_generated/server";

export const putReport = internalMutation({
  args: { runId: v.string(), json: v.string() },
  handler: async (ctx, { runId, json }) => {
    for (const r of await ctx.db.query("reports").collect()) await ctx.db.delete(r._id);
    await ctx.db.insert("reports", { runId, json, pushedAt: Date.now() });
  },
});

export const putSnapshot = internalMutation({
  args: { runId: v.string(), json: v.string() },
  handler: async (ctx, { runId, json }) => {
    const prev = await ctx.db
      .query("snapshots")
      .withIndex("by_run", (q) => q.eq("runId", runId))
      .unique();
    if (prev) await ctx.db.patch(prev._id, { json });
    else await ctx.db.insert("snapshots", { runId, json });
  },
});

export const snapshotIds = internalQuery({
  args: {},
  handler: async (ctx) => (await ctx.db.query("snapshots").collect()).map((s) => s.runId),
});

// Copy documents written on the Claude page across, keyed by their ids there,
// so both places show the same comments while they run side by side.
export const upsertEntries = internalMutation({
  args: { collection: v.string(), docs: v.array(v.object({ id: v.string(), data: v.any() })) },
  handler: async (ctx, { collection, docs }) => {
    let added = 0;
    for (const d of docs) {
      const prev = await ctx.db
        .query("entries")
        .withIndex("by_collection_doc", (q) => q.eq("collection", collection).eq("docId", d.id))
        .unique();
      if (prev) {
        if (JSON.stringify(prev.data) !== JSON.stringify(d.data))
          await ctx.db.patch(prev._id, { data: d.data, updatedAt: Date.now() });
      } else {
        await ctx.db.insert("entries", { collection, docId: d.id, data: d.data, updatedAt: Date.now() });
        added++;
      }
    }
    return added;
  },
});

export const listEntries = internalQuery({
  args: { collection: v.string() },
  handler: async (ctx, { collection }) =>
    (
      await ctx.db
        .query("entries")
        .withIndex("by_collection", (q) => q.eq("collection", collection))
        .collect()
    ).map((r) => ({ id: r.docId, data: r.data })),
});

// Who may log in. Emails live only in Convex, never in the repo.
export const putPerson = internalMutation({
  args: { email: v.string(), name: v.string(), owner: v.boolean(), by: v.optional(v.string()) },
  handler: async (ctx, args) => {
    const email = args.email.trim().toLowerCase();
    const prev = await ctx.db
      .query("people")
      .withIndex("by_email", (q) => q.eq("email", email))
      .unique();
    const by = args.owner ? "owner" : args.by || prev?.by || `p_${crypto.randomUUID().slice(0, 12)}`;
    const row = { email, name: args.name, owner: args.owner, by, who: args.owner ? "owner" : by };
    if (prev) await ctx.db.patch(prev._id, row);
    else await ctx.db.insert("people", row);
    return row.who;
  },
});

export const listPeople = internalQuery({
  args: {},
  handler: async (ctx) =>
    (await ctx.db.query("people").collect()).map((p) => ({
      name: p.name,
      owner: p.owner,
      who: p.who,
      signedUp: !!p.userId,
    })),
});
