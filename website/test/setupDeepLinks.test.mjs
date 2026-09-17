import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

// A checklist row that points nowhere is the old inline form with the form taken out. These are the
// three positions the five rows name, and none of them existed before.
test("the AI CLI agents page has a door of its own", () => {
  const view = read("ConnectorsView.jsx");
  assert.match(view, /#?cli-agents/);
  assert.match(view, /setOpen\(\{ kind: "agents" \}\)/);
});

test("Settings can be opened on a page and a group", () => {
  const view = read("SettingsView.jsx");
  assert.match(view, /settings=\(\[\\w-\]\+\)/);
  // the brief's own regex left the `^` unescaped, so it read as a start-of-string anchor
  // instead of a literal caret inside "[^&]" - fixed here to actually match the source.
  assert.match(view, /group=\(\[\^&\]\+\)/);
  assert.match(view, /decodeURIComponent/);
  // consumed once, like every other hash in the app - or Back reopens it
  assert.match(view, /history\.replaceState/);
});

test("Docs can be opened on the name field", () => {
  const view = read("DocsView.jsx");
  assert.match(view, /#?owner/);
  assert.match(view, /scrollIntoView/);
});
