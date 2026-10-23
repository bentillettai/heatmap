// Split site/template.html (the page the daily run builds) into its markup and
// script, so the website runs the same page with data from Convex.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "..", "..", "site", "template.html"), "utf8");
const DATA_TAG = '<script type="application/json" id="heatmap-data">__HEATMAP_DATA__</script>';
const at = html.indexOf(DATA_TAG);
if (at < 0) throw new Error("template.html: data tag not found");
const markup = html
  .slice(0, at)
  .replace(/<meta [^>]*>\n?/g, "")
  .replace(/<title>.*?<\/title>\n?/, "");
const rest = html.slice(at + DATA_TAG.length);
const m = rest.match(/<script>([\s\S]*)<\/script>/);
if (!m) throw new Error("template.html: page script not found");
mkdirSync(join(here, "..", "generated"), { recursive: true });
writeFileSync(
  join(here, "..", "generated", "page.ts"),
  `// Generated from site/template.html by scripts/split-template.mjs. Don't edit.\n` +
    `export const MARKUP = ${JSON.stringify(markup)};\nexport const SCRIPT = ${JSON.stringify(m[1])};\n`,
);
console.log(`page: ${Math.round(markup.length / 1024)} KB markup, ${Math.round(m[1].length / 1024)} KB script`);
