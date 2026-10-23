# Heatmap website

A login website that shows the same page as the Claude artifact, for people
who can't use Claude at work. Next.js on Vercel, data and logins in Convex.
There is no AI in the site: the daily run (`CLAUDE.md`) builds the report and
pushes it here with `tools/convex_sync.py push`, then pulls back what people
wrote with `pull`.

- `app/` runs `site/template.html` unchanged. `scripts/split-template.mjs`
  splits it into markup and script at build time; `app/host.ts` gives the
  script the `window.claude` database and user it expects, backed by Convex.
- `convex/` holds the report, the run reports, votes, comments and notes
  (`entries`, same shape and ids as the Claude page), and the invite list
  (`people`). Log in is email and password, invite only.
- `convex/sync.ts` is internal: only the pipeline calls it, with the deploy key.

## Set up (once)

1. Create a Convex project called `heatmap`, and a production deploy key for
   it (Project settings, Deploy keys).
2. Create a Vercel project from this repo with root directory `web` (the
   build reads `../site/template.html`, so keep "include files outside the
   root directory" on). `vercel.json` sets the build command, which deploys
   the Convex functions first. Add `CONVEX_DEPLOY_KEY` (production key) to the
   project's environment variables. Only production builds (pushes to `main`)
   run: `ignoreCommand` skips previews of other branches, which have no key.
3. Deploy, then set the auth signing keys on the Convex deployment, using the
   site's address:
   `CONVEX_DEPLOY_KEY=... node scripts/auth-keys.mjs https://<site>.vercel.app`
4. Copy the data and invite people (from the repo root, with the key set):
   ```
   python3 tools/convex_sync.py push --all
   python3 tools/convex_sync.py mirror <ArtifactData out_dir>
   python3 tools/convex_sync.py invite <ben's email> ben --owner
   python3 tools/convex_sync.py invite henry@invite.pending Henry --by <Henry's id on the Claude page>
   ```
   `--by` keeps Henry's earlier comments and votes as his. A `.pending` email
   is a placeholder: when ben invites Henry's real email under the same name
   on the site's Invite people page (`/invite`, owner only), that row is
   updated and keeps the id. Emails are stored only in Convex, never in this
   repo.
5. Put the same `CONVEX_DEPLOY_KEY` in the cloud environment the daily run uses.

People then open the site, choose "Create your account" with their invited
email, and pick a password.

## Develop

```
npm install
CONVEX_AGENT_MODE=anonymous npx convex dev   # local backend, no account needed
node scripts/auth-keys.mjs http://localhost:3000
npm run dev
```

For the local backend, `tools/convex_sync.py` takes `CONVEX_URL` and
`CONVEX_ADMIN_KEY` (from `.convex/local/default/config.json`) instead of the
deploy key.
