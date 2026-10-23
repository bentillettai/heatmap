import { authTables } from "@convex-dev/auth/server";
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  ...authTables,

  // Who may log in. Only these emails can create an account. `who` and `by`
  // are the ids the page writes on votes and comments; Henry keeps the ids he
  // had on the Claude page, so his old and new comments read as one person.
  people: defineTable({
    email: v.string(),
    name: v.string(),
    who: v.string(),
    by: v.string(),
    owner: v.boolean(),
    userId: v.optional(v.id("users")),
  })
    .index("by_email", ["email"])
    .index("by_user", ["userId"])
    .index("by_by", ["by"]),

  // What people write on the page, in the same shape as the Claude page's
  // database: feedback/<card>~<who>, runfeedback/<run>~<who>, comments/<id>,
  // notes/<id>. The daily run reads these back (tools/convex_sync.py pull).
  entries: defineTable({
    collection: v.string(),
    docId: v.string(),
    data: v.any(),
    updatedAt: v.number(),
  })
    .index("by_collection", ["collection"])
    .index("by_collection_doc", ["collection", "docId"]),

  // The latest report (the page's data, as built by tools/heatmap.py), and a
  // frozen report per run for the Runs tab. Stored as JSON text.
  reports: defineTable({ runId: v.string(), json: v.string(), pushedAt: v.number() }),
  snapshots: defineTable({ runId: v.string(), json: v.string() }).index("by_run", ["runId"]),
});
