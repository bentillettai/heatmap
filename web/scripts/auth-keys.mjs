// Set the signing keys Convex Auth needs on a deployment (once per deployment).
// Uses CONVEX_DEPLOY_KEY when set, otherwise the dev deployment in .env.local.
//   node scripts/auth-keys.mjs https://<site>.vercel.app
import { execFileSync } from "node:child_process";
import { exportJWK, exportPKCS8, generateKeyPair } from "jose";

const siteUrl = process.argv[2];
if (!siteUrl) throw new Error("usage: node scripts/auth-keys.mjs SITE_URL");
const keys = await generateKeyPair("RS256", { extractable: true });
const privateKey = (await exportPKCS8(keys.privateKey)).trimEnd().replace(/\n/g, " ");
const jwks = JSON.stringify({ keys: [{ use: "sig", ...(await exportJWK(keys.publicKey)) }] });
const set = (name, value) =>
  execFileSync("npx", ["convex", "env", "set", "--", name, value], { stdio: ["ignore", "ignore", "inherit"] });
set("JWT_PRIVATE_KEY", privateKey);
set("JWKS", jwks);
set("SITE_URL", siteUrl);
console.log("set JWT_PRIVATE_KEY, JWKS and SITE_URL");
