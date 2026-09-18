import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

// The acts pack (2026-09-18): the chat assistant runs the app by name, and what it changed is on the
// Settings page with an undo beside it; a script started by name opens its road on the desktop.
test("the Settings page lists what the assistant changed and offers the undo", () => {
  const view = read("../src/SettingsView.jsx");
  assert.match(view, /api\.get\("\/api\/audit\/assistant"/);
  assert.match(view, /<AssistantChanges \/>/);
  assert.match(view, /What the assistant changed/);
  assert.match(view, /api\.post\(`\/api\/operations\/\$\{undo\.id\}\/execute`, \{ version: undo\.version \}\)/, "the undo is the same execute road as any proposal");
  const server = read("../../taskuary/server.py");
  assert.match(server, /@app\.get\('\/api\/audit\/assistant'\)/);
});

test("a script started by name opens its road: the walk's Next, the set-up tour, or the composer", () => {
  const view = read("../src/AssistantView.jsx");
  const at = view.indexOf("const script = res?.outcome?.script;");
  assert.notEqual(at, -1);
  const block = view.slice(at, at + 400);
  assert.match(block, /advance\(\)/); assert.match(block, /await setup\(\)/); assert.match(block, /askSetup\(\)/);
});

test("the instant tiers are one set the catalogue and the receipts both read", () => {
  const cat = read("../../taskuary/toolcatalog.py");
  assert.match(cat, /INSTANT = frozenset\(\{/);
  for (const k of ["report.run", "setting.set", "connection.pause", "script.start"]) assert.ok(cat.includes(`'${k}'`), k);
  assert.doesNotMatch(cat.slice(cat.indexOf("INSTANT = frozenset"), cat.indexOf("def is_instant")), /report\.delete/, "deleting asks first");
});
