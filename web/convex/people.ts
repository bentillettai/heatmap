import { getAuthUserId } from "@convex-dev/auth/server";
import { v } from "convex/values";
import type { QueryCtx } from "./_generated/server";
import { query } from "./_generated/server";

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
