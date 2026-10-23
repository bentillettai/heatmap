import { getAuthUserId } from "@convex-dev/auth/server";
import { ConvexError, v } from "convex/values";
import type { MutationCtx, QueryCtx } from "./_generated/server";
import { mutation, query } from "./_generated/server";

export async function currentPerson(ctx: QueryCtx) {
  const userId = await getAuthUserId(ctx);
  if (!userId) return null;
  return await ctx.db
    .query("people")
    .withIndex("by_user", (q) => q.eq("userId", userId))
    .unique();
}

export const me = query({
  args: {},
  handler: async (ctx) => {
    const p = await currentPerson(ctx);
    return p && { id: p.by, name: p.name, isOwner: p.owner, who: p.who };
  },
});

// Display names for the ids on comments and votes, as the Claude page's
// user.profiles() returns them.
export const profiles = query({
  args: { ids: v.array(v.string()) },
  handler: async (ctx, { ids }) => {
    if (!(await currentPerson(ctx))) return {};
    const out: Record<string, { name: string }> = {};
    for (const id of ids.slice(0, 64)) {
      const p = await ctx.db
        .query("people")
        .withIndex("by_by", (q) => q.eq("by", id))
        .first();
      if (p) out[id] = { name: p.name };
    }
    return out;
  },
});

// Add someone to the invite list, or update them. A person added before their
// email was known (a placeholder email, not signed up) is matched by name, so
// they keep the id their earlier comments carry.
export async function upsertPerson(
  ctx: MutationCtx,
  args: { email: string; name: string; owner: boolean; by?: string },
) {
  const email = args.email.trim().toLowerCase();
  const name = args.name.trim();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || !name) throw new ConvexError("Give a name and a valid email.");
  let prev = await ctx.db
    .query("people")
    .withIndex("by_email", (q) => q.eq("email", email))
    .unique();
  if (!prev) {
    const all = await ctx.db.query("people").collect();
    prev = all.find((p) => !p.userId && p.name.toLowerCase() === name.toLowerCase() && p.email.endsWith(".pending")) ?? null;
  }
  const by = args.owner ? "owner" : args.by || prev?.by || `p_${crypto.randomUUID().slice(0, 12)}`;
  const row = { email, name, owner: args.owner, by, who: args.owner ? "owner" : by };
  if (prev) await ctx.db.patch(prev._id, row);
  else await ctx.db.insert("people", row);
  return row;
}

async function requireOwner(ctx: QueryCtx) {
  const p = await currentPerson(ctx);
  if (!p?.owner) throw new ConvexError("Only ben can manage the invite list.");
  return p;
}

export const list = query({
  args: {},
  handler: async (ctx) => {
    const p = await currentPerson(ctx);
    if (!p?.owner) return null;
    return (await ctx.db.query("people").collect()).map((x) => ({
      id: x._id,
      email: x.email,
      name: x.name,
      owner: x.owner,
      signedUp: !!x.userId,
    }));
  },
});

export const invite = mutation({
  args: { email: v.string(), name: v.string() },
  handler: async (ctx, args) => {
    await requireOwner(ctx);
    await upsertPerson(ctx, { ...args, owner: false });
  },
});

export const uninvite = mutation({
  args: { id: v.id("people") },
  handler: async (ctx, { id }) => {
    const me = await requireOwner(ctx);
    if (id === me._id) throw new ConvexError("You can't remove yourself.");
    const p = await ctx.db.get(id);
    if (!p) return;
    // Their comments stay. Their login stops working.
    if (p.userId) {
      for (const s of await ctx.db.query("authSessions").withIndex("userId", (q) => q.eq("userId", p.userId!)).collect())
        await ctx.db.delete(s._id);
      for (const a of await ctx.db.query("authAccounts").withIndex("userIdAndProvider", (q) => q.eq("userId", p.userId!)).collect())
        await ctx.db.delete(a._id);
      await ctx.db.delete(p.userId);
    }
    await ctx.db.delete(id);
  },
});
