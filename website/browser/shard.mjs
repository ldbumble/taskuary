// ONE PART OF THE BROWSER SUITE (2026-10-21): the suite ran file after file on one machine and outgrew its 10 minutes; CI now runs it
// as N parts at once. Each part takes every Nth file of package.json's test:browser list, so a file added there is run by exactly one
// part and nobody keeps a second list. Usage: node browser/shard.mjs <part 1..N> <N>
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const [part, of] = process.argv.slice(2).map(Number);
if (!(part >= 1 && of >= 1 && part <= of)) { console.error("usage: node browser/shard.mjs <part 1..N> <N>"); process.exit(2); }
const all = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")).scripts["test:browser"].split(/\s+/).filter((a) => a.endsWith(".test.mjs"));
const mine = all.filter((_, i) => i % of === part - 1);
console.log(`part ${part} of ${of}: ${mine.length} of ${all.length} files - ${mine.join(" ")}`);
const r = spawnSync(process.execPath, ["--test", "--test-concurrency=1", ...mine], { stdio: "inherit" });
process.exit(r.status ?? 1);
