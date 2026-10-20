// The Advisor's strip is one line (2026-10-20): the CSS clamps it, the cut sentence is its tooltip, and main.jsx installs that once.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { cut, titleCut } from "../src/oneLine.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("every .tq-next-txt is one line with an ellipsis, and the strip's buttons never shrink", () => {
  const css = read("assistantView.css");
  assert.match(css, /\.tq-next-txt \{[^}]*white-space: nowrap; overflow: hidden; text-overflow: ellipsis;/);
  assert.match(css, /\.tq-next > \*:not\(\.tq-next-txt\) \{ flex-shrink: 0; \}/);
  assert.match(read("main.jsx"), /import \{ installOneLine \} from "\.\/oneLine\.js";\ninstallOneLine\(\);/);
});

test("a line that was cut gets the whole sentence as its tooltip; one that fits has none", () => {
  const el = (sw, cw) => ({ scrollWidth: sw, clientWidth: cw, innerText: "the whole sentence", title: "", removed: false,
    removeAttribute() { this.removed = true; this.title = ""; } });
  const long = el(900, 400), short = el(200, 400);
  assert.equal(cut(long), true); assert.equal(cut(short), false);
  titleCut({ target: { closest: () => long } }); assert.equal(long.title, "the whole sentence");
  titleCut({ target: { closest: () => short } }); assert.equal(short.removed, true);
  titleCut({ target: { closest: () => null } });           // not a strip: nothing happens
});
