import { v } from "convex/values";
import { query } from "./_generated/server";
import { currentPerson } from "./people";

export const latest = query({
  args: {},
  handler: async (ctx) => {
    if (!(await currentPerson(ctx))) return null;
    const r = await ctx.db.query("reports").order("desc").first();
    return r && { runId: r.runId, json: r.json };
  },
});

export const snapshot = query({
  args: { runId: v.string() },
  handler: async (ctx, { runId }) => {
    if (!(await currentPerson(ctx))) return null;
    const s = await ctx.db
      .query("snapshots")
      .withIndex("by_run", (q) => q.eq("runId", runId))
      .unique();
    return s && s.json;
  },
});
