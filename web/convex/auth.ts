import { Password } from "@convex-dev/auth/providers/Password";
import { convexAuth } from "@convex-dev/auth/server";
import { ConvexError } from "convex/values";
import type { MutationCtx } from "./_generated/server";

export const { auth, signIn, signOut, store, isAuthenticated } = convexAuth({
  providers: [
    Password({
      profile(params) {
        return { email: String(params.email ?? "").trim().toLowerCase() };
      },
    }),
  ],
  callbacks: {
    // Invite only: an account can be made only for an email in `people`.
    async createOrUpdateUser(genericCtx, args) {
      const ctx = genericCtx as unknown as MutationCtx;
      if (args.existingUserId) return args.existingUserId;
      const email = String(args.profile.email ?? "").toLowerCase();
      const person = await ctx.db
        .query("people")
        .withIndex("by_email", (q) => q.eq("email", email))
        .unique();
      if (!person) throw new ConvexError("This email isn't on the invite list. Ask ben to add it.");
      const userId = await ctx.db.insert("users", { email, name: person.name });
      await ctx.db.patch(person._id, { userId });
      return userId;
    },
  },
});
