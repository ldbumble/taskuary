// The Advisor's strip is one line (2026-10-20): the CSS clamps it, the cut sentence is its tooltip, and main.jsx installs that once.
import test from "node:test";
import assert from "node:assert/strict";

import { cut, titleCut } from "../src/oneLine.js";


test("a line that was cut gets the whole sentence as its tooltip; one that fits has none", () => {
  const el = (sw, cw) => ({ scrollWidth: sw, clientWidth: cw, innerText: "the whole sentence", title: "", removed: false,
    removeAttribute() { this.removed = true; this.title = ""; } });
  const long = el(900, 400), short = el(200, 400);
  assert.equal(cut(long), true); assert.equal(cut(short), false);
  titleCut({ target: { closest: () => long } }); assert.equal(long.title, "the whole sentence");
  titleCut({ target: { closest: () => short } }); assert.equal(short.removed, true);
  titleCut({ target: { closest: () => null } });           // not a strip: nothing happens
});
