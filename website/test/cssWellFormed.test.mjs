// EVERY STYLESHEET CLOSES WHAT IT OPENS. Vite joins the app's CSS into one file, so a rule cut in half in one sheet breaks the NEXT
// sheet's first rule: 2026-11-06 a two-line `.tq-cc-term` lost its first line in diffView.css, its orphaned `... cursor: pointer; }`
// became part of the selector of `.tq-dash { --d-* }` after it, the browser dropped that rule, and every dashboard and report chart
// lost its palette - bars and legend swatches drawn in `var(--d-s1)` with no value, the cards transparent on the warm ground (2026-11-07).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const sheets = (d) => readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? sheets(join(d, e.name)) : e.name.endsWith(".css") ? [join(d, e.name)] : []));

// the problems in one sheet: a `}` with nothing open, a block left open at the end, or declarations between rules (a top-level prelude
// with a `;` that is not an at-rule's own, e.g. `@import ...;`)
function cssProblems(css) {
  const t = css.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, "")).replace(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g, '""');
  const out = []; let depth = 0, pre = "", line = 1;
  for (const ch of t) {
    if (ch === "\n") line++;
    if (ch === "{") { depth++; pre = ""; }
    else if (ch === "}") { if (!depth) out.push(`line ${line}: a } with nothing open`); depth = Math.max(0, depth - 1); pre = ""; }
    else if (depth) continue;
    else if (ch !== ";") pre += ch;
    else { if (!/^\s*@/.test(pre)) out.push(`line ${line}: declarations outside a rule: ${pre.trim().slice(0, 60)}`); pre = ""; }
  }
  if (depth) out.push(`${depth} block(s) left open at the end`);
  return out;
}

test("the checker sees the 2026-11-06 break and passes a sound sheet", () => {
  assert.deepEqual(cssProblems(".a { color: red; }\n@import url(x.css);\n@media (x) { .b { c: d; } }\n.c::after { content: '}'; }"), []);
  assert.ok(cssProblems(".a { b: c; }\n  background: #f4f1ec; cursor: pointer; }\n.tq-dash { --d-s1: #3f77b3; }").length);
  assert.ok(cssProblems(".a { b: c;").length);
});

test("every stylesheet the app bundles is well formed", () => {
  const bad = sheets(SRC).map((f) => [f.slice(SRC.length), cssProblems(readFileSync(f, "utf8"))]).filter(([, p]) => p.length);
  assert.deepEqual(bad, [], bad.map(([f, p]) => `${f}: ${p.join("; ")}`).join("\n"));
});
