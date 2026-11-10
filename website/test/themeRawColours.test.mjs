// Dark mode drifts one hand-typed colour at a time: a new `bgcolor: "#fff"` is a white box in the night palette.
// Each file may hold no more raw colours than it does now (rawColours.json). A new colour takes a token -
// "var(--tq-panel, #fff)" - or, when it truly must stay fixed (brand art, terminal palette, a solid fill with its
// own text), its file's count is raised in rawColours.json on purpose. Regenerate: node test/themeRawColours.test.mjs --write
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url)), src = path.join(here, "../src"), base = path.join(here, "rawColours.json");
const walk = (d) => readdirSync(d, { withFileTypes: true }).flatMap((e) => e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]);
// a token's own light fallback is not raw, nor is "#278" in a comment (an issue); anything else spelled as hex or rgb()/rgba() is
const uncommented = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|\s)\/\/.*$/gm, "$1");
export const rawCount = (s) => uncommented(s).replace(/var\(--tq-[\w-]+,[^)]*\)/g, "").match(/#[0-9a-f]{3,8}\b|rgba?\(\s*\d/gi)?.length || 0;
export const counts = () => Object.fromEntries(walk(src).filter((f) => /\.(jsx?|css)$/.test(f))
  .map((f) => [path.relative(src, f).replaceAll("\\", "/"), rawCount(readFileSync(f, "utf8"))]).filter(([, n]) => n).sort());

if (process.argv.includes("--write")) writeFileSync(base, JSON.stringify(counts(), null, 1) + "\n");
else {
  test("a token's fallback is not counted, a bare colour is", () => {
    assert.equal(rawCount(`// see #278
bgcolor: "var(--tq-panel, #fff)", color: "#262521", bd: "rgba(0,0,0,.1)", g: "rgb(var(--tq-panel-rgb, 1 2 3) / .9)"`), 2);
  });
  test("no file gains a raw colour: new colours use a --tq token, so dark mode follows", () => {
    const allowed = JSON.parse(readFileSync(base, "utf8"));
    const over = Object.entries(counts()).filter(([f, n]) => n > (allowed[f] || 0)).map(([f, n]) => `${f}: ${n} raw colours, ${allowed[f] || 0} allowed`);
    assert.deepEqual(over, [], "write the new colour as var(--tq-<name>, <light colour>) (names: src/appPalette.js); if it must stay fixed, raise its count in test/rawColours.json");
  });
}
