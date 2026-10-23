// The page's shared database, the same four collections the Claude page
// uses. The web page calls these through a small adapter (app/host.ts), so
// the page script runs unchanged in both places.
import { ConvexError, v } from "convex/values";
import type { MutationCtx } from "./_generated/server";
import { mutation, query } from "./_generated/server";
import { currentPerson } from "./people";

const COLLECTIONS = ["feedback", "runfeedback", "comments", "notes"] as const;
type Collection = (typeof COLLECTIONS)[number];
const collection = v.union(...COLLECTIONS.map((c) => v.literal(c)));
const MAX_TEXT = 8000;

const str = (x: unknown, max = 200) => (typeof x === "string" ? x.slice(0, max) : null);

// Keep only the fields each collection has, and stamp who wrote it from the
// login rather than trusting the page.
function clean(
  name: Collection,
  data: Record<string, unknown>,
  person: { by: string; who: string; owner: boolean },
): Record<string, unknown> {
  const stamp = { by: person.by, who: person.who, owner: person.owner };
  const now = new Date().toISOString();
  switch (name) {
    case "feedback":
    case "runfeedback": {
      const key = name === "feedback" ? "card" : "run";
      const vote = data.vote === "up" || data.vote === "down" ? data.vote : null;
      return { [key]: str(data[key]), vote, why: str(data.why, MAX_TEXT) ?? "", updated: now, ...stamp };
    }
    case "comments":
      return {
        kind: data.kind === "run" ? "run" : "card",
        target: str(data.target),
        text: str(data.text, MAX_TEXT) ?? "",
        created: now,
        run: str(data.run),
        ...stamp,
      };
    case "notes":
      return { text: str(data.text, MAX_TEXT) ?? "", area: str(data.area), created: now, ...stamp };
  }
}

async function person(ctx: MutationCtx) {
  const p = await currentPerson(ctx);
  if (!p) throw new ConvexError("Sign in to comment.");
  return p;
}

async function find(ctx: MutationCtx, name: string, docId: string) {
  return await ctx.db
    .query("entries")
    .withIndex("by_collection_doc", (q) => q.eq("collection", name).eq("docId", docId))
    .unique();
}

export const list = query({
  args: { collection },
  handler: async (ctx, args) => {
    if (!(await currentPerson(ctx))) return [];
    const rows = await ctx.db
      .query("entries")
      .withIndex("by_collection", (q) => q.eq("collection", args.collection))
      .collect();
    return rows.map((r) => ({ id: r.docId, data: r.data }));
  },
});

// Votes are one document per person per card or run: <target>~<who>.
export const set = mutation({
  args: { collection, id: v.string(), data: v.any() },
  handler: async (ctx, args) => {
    const p = await person(ctx);
    if (args.collection !== "feedback" && args.collection !== "runfeedback")
      throw new ConvexError("Only votes are set by id.");
    const data = clean(args.collection, args.data ?? {}, p);
    const target = data[args.collection === "feedback" ? "card" : "run"];
    if (!target || args.id !== `${target}~${p.who}`) throw new ConvexError("That vote isn't yours.");
    const prev = await find(ctx, args.collection, args.id);
    if (prev) await ctx.db.patch(prev._id, { data, updatedAt: Date.now() });
    else await ctx.db.insert("entries", { collection: args.collection, docId: args.id, data, updatedAt: Date.now() });
  },
});

export const add = mutation({
  args: { collection, data: v.any() },
  handler: async (ctx, args) => {
    const p = await person(ctx);
    if (args.collection !== "comments" && args.collection !== "notes")
      throw new ConvexError("Only comments and notes are added.");
    const data = clean(args.collection, args.data ?? {}, p);
    if (!String(data.text).trim()) throw new ConvexError("Nothing to save.");
    const docId = Array.from(crypto.getRandomValues(new Uint8Array(15)), (b) => (b % 36).toString(36)).join("");
    await ctx.db.insert("entries", { collection: args.collection, docId, data, updatedAt: Date.now() });
    return docId;
  },
});

export const remove = mutation({
  args: { collection, id: v.string() },
  handler: async (ctx, args) => {
    const p = await person(ctx);
    const row = await find(ctx, args.collection, args.id);
    if (!row) return;
    if (row.data?.who !== p.who && !p.owner) throw new ConvexError("You can only delete your own.");
    await ctx.db.delete(row._id);
  },
});
