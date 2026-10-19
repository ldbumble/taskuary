import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");

// The acts pack (2026-09-18) made the chat run the app by name, with an undo on Settings. The owner, 2026-10-19: "no take it back button.
// hate that. the assistant again should just be a router" - what the assistant changed is still listed there, as a record, and a typed
// act brings up its page or its button (concierge._route); setting Taskuary up is the Setup button, never a script.
test("the Settings page lists what the assistant changed, with no undo", () => {
  const view = read("../src/SettingsView.jsx");
  assert.match(view, /api\.get\("\/api\/audit\/assistant"/);
  assert.match(view, /<AssistantChanges \/>/);
  assert.match(view, /What the assistant changed/);
  assert.doesNotMatch(view, /Undo the last change|\/api\/operations\/\$\{undo\.id\}/);
  const server = read("../../taskuary/server.py");
  assert.match(server, /@app\.get\('\/api\/audit\/assistant'\)/);
  assert.doesNotMatch(server, /assistant_last_undo/);
});

test("no script sets Taskuary up from the chat: setup is the Setup button at the top", () => {
  assert.doesNotMatch(read("../src/AssistantView.jsx"), /set up taskuary\/i\.test/);
  assert.doesNotMatch(read("../../taskuary/appfacts.py"), /'set up Taskuary'/);
  assert.match(read("../../taskuary/toolcatalog.py"), /'script\.start': +'start a script by its name: walk me through my tasks \| set up a report'/);
});

test("nothing the chat names runs at once: each tool is the button the owner presses", () => {
  const cat = read("../../taskuary/toolcatalog.py");
  assert.doesNotMatch(cat, /def is_instant|with an undo/);
  assert.match(read("../../taskuary/concierge.py"), /def _route\(store/);
});

