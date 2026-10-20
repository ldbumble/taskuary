// Outside the demo build demoApi.js is demoOff.js (vite.config.js): every name a module imports from it must exist there,
// answer "not the demo", and the recording must not be reachable from the stand-in.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import * as off from "../src/demoOff.js";

const src = new URL("../src/", import.meta.url);
const files = readdirSync(src).filter((f) => /\.(jsx?|mjs)$/.test(f) && f !== "demoApi.js");

test("every name imported from demoApi.js is answered by demoOff.js", () => {
  const names = new Set();
  for (const f of files) {
    const s = readFileSync(new URL(f, src), "utf8");
    for (const m of s.matchAll(/^import\s+([^;]*?)\s+from\s+["']\.\/demoApi\.js["']/gm)) {
      const [, dflt, named] = /^(\w+)?\s*,?\s*(?:\{([^}]*)\})?$/.exec(m[1].trim()) || [];
      if (dflt) names.add("default");
      for (const n of (named || "").split(",").map((x) => x.trim().split(/\s+as\s+/)[0]).filter(Boolean)) names.add(n);
    }
    for (const m of s.matchAll(/\{\s*([^{}]*)\}\s*=\s*await import\(["']\.\/demoApi\.js["']\)/g))
      for (const n of m[1].split(",").map((x) => x.trim()).filter(Boolean)) names.add(n);
  }
  assert.ok(names.has("DEMO"), "the scan found the readers");
  for (const n of names) assert.ok(n in off, `demoOff.js has no ${n}`);
  assert.equal(off.DEMO, false); assert.equal(off.DEMO_GUIDED, false);
});

test("the stand-in reaches nothing of the recording", () => {
  const s = readFileSync(new URL("demoOff.js", src), "utf8");
  assert.doesNotMatch(s, /^\s*import\b/m);
});

test("the alias is off exactly when VITE_DEMO is 1", () => {
  const cfg = readFileSync(new URL("../vite.config.js", import.meta.url), "utf8");
  assert.match(cfg, /VITE_DEMO === "1" \? \[\]/);
  assert.match(cfg, /demoApi\\.js\$\/, replacement: .*demoOff\.js/);
});
