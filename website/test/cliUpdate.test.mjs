// The Update button on the AI CLI agents page.
//
// From the owner, 2026-09-11: codex was installed, signed in, and refused every single run because
// the model pinned in its own config needed a newer Codex. "Installed" was true and useless, and
// the page offered nothing to press.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("install and update are one errand with two verbs, and one phase between them", () => {
  const src = read("cliInstall.jsx");
  assert.match(src, /path: "\/api\/cli\/install"/);
  assert.match(src, /path: "\/api\/cli\/update"/);
  assert.match(src, /const install = useCallback\(\(cli\) => run\(cli, "install"\)/);
  assert.match(src, /const update = useCallback\(\(cli\) => run\(cli, "update"\)/);
  // one server-side phase, polled by both - so a second press cannot report the first run's result
  assert.equal(src.match(/api\.get\("\/api\/cli\/install\/state"\)/g).length, 1);
  assert.match(src, /data\.name && data\.name !== name/);
});

test("the button is drawn only over a road that exists", () => {
  const src = read("cliInstall.jsx");
  assert.match(src, /export const UpdateLine = /);
  assert.match(src, /if \(!cli\?\.updatable\) return null;/);   // the server decides, not the page
  assert.match(src, /busy === recipeOf\(cli\) \? "updating…" : "Update"/);
});

test("an installed CLI on the AI CLI agents page can be updated in place", () => {
  const panel = read("AgentsPanel.jsx");
  assert.match(panel, /import \{ useCliInstall, InstallLine, UpdateLine \}/);
  // the hook's shape is the page's business - assert only that it takes `update` out and uses it,
  // or this breaks every time the panel gains an option it needs from the same hook
  assert.match(panel, /const \{[^}]*\bupdate\b[^}]*\} = useCliInstall\(/);
  // Update rides with the INSTALLED branch and Install with the other - the shape of that branch
  // is the page's to change, so match the wiring and not its punctuation
  assert.match(panel, /<UpdateLine cli=\{cli\}[^>]*onUpdate=\{async \(\) => \{ if \(await update\(cli\)\) await load\(\); \}\}/);
  assert.match(panel, /cli\.installed \?[\s\S]{0,400}?<UpdateLine/);
  assert.match(panel, /<InstallLine cli=\{cli\}[^>]*onInstall=/);
});

test("the server's own words are what the owner reads when it finishes", () => {
  const src = read("cliInstall.jsx");
  // an updater that says what it did beats the page saying "done" over the top of it
  assert.match(src, /data\.phase === "done"[\s\S]{0,120}?text: data\.detail \|\|/);
});
