// The people pages under Settings → Docs (spec 2026-10-12, build step 4): the rail lists them from /api/people/pages
// and the viewer draws one by its address. Source regexes, the way the rail's other tests pin it (setupWalk, canvasItem).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const settings = fs.readFileSync(new URL("../src/SettingsView.jsx", import.meta.url), "utf8");
const docs = fs.readFileSync(new URL("../src/DocsView.jsx", import.meta.url), "utf8");

test("the Docs rail lists the people pages and the viewer draws one by its address", () => {
  assert.match(settings, /key: "g:people", label: "People"/);
  assert.match(settings, /people\.map\(\(p\) => \(\{ key: `pp:\$\{p\.name\}`, label: p\.who/);
  assert.match(docs, /api\.get\("\/api\/people\/pages"\)/);
  assert.match(docs, /onCatalog\?\.\(\{ profiles: profs, playbooks: books, people \}\)/);
  assert.match(docs, /isPerson\(docName\)/);
});
