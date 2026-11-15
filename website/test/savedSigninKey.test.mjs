import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// the owner, 2026-10-25: "Yes: TOTP codes in the sign-in vault". A saved sign-in's row keeps its authenticator key - write-only: the
// row says one is kept, the key goes out once to the owner-only route, and nothing ever reads it back
test("a saved sign-in's row keeps or drops its authenticator key, and never shows it", () => {
  const ss = read("SavedSignins.jsx");
  assert.match(ss, /api\.post\(`\/api\/signins\/\$\{encodeURIComponent\(site\)\}\/code`, \{ key: value \}\)/);
  assert.match(ss, /\{r\.code \? "Remove authenticator key" : "Add authenticator key"\}/);
  assert.match(ss, /\{r\.code \? " · authenticator code" : ""\}/, "the row says one is kept");
  assert.match(ss, /<TextField size="small" type="password" autoComplete="off"/, "typed as a secret, never autofilled");
  assert.match(ss, /error=\{!!keyErr\} helperText=\{keyErr \|\| " "\}/, "a mistyped key is said under its box");
  assert.doesNotMatch(ss, /api\.get\(`\/api\/signins\/[^`]*\/code`/, "no read of a key");
  // Remove still says Removing… only for a removal, not while a key saves
  assert.match(ss, /busy === r\.site && what === "remove" \? "Removing…" : "Remove"/);
});

// REMOVE IS ONE PRESS, AND LEAVES AN UNDO LINE (the owner, 2026-11-15; the press asks nothing - only a connection card asks). The line is the
// one every Remove leaves (Removed.jsx: removeNow announces, UndoLine draws and restores through /api/deleted) - no second undo of its own
test("removing a saved sign-in asks nothing and leaves the app's own Undo line", async () => {
  const fs = await import("node:fs"), read = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8"), ss = read("SavedSignins.jsx");
  assert.match(ss, /import \{ UndoLine, removeNow \} from "\.\/Removed\.jsx";/);
  assert.match(ss, /await removeNow\(\(\) => api\.delete\(`\/api\/signins\/\$\{encodeURIComponent\(site\)\}`\), "signin", site\); await load\(\);/);
  assert.match(ss, /<UndoLine kinds=\{\["signin"\]\} onRestored=\{load\}/);
  assert.equal(ss.match(/\{undo\}/g).length, 2, "under the list, and where the last one was removed and the list is empty");
  assert.doesNotMatch(ss, /confirm|Are you sure|setAsk\(/i, "no question before the press");
  assert.match(ss, /onClick=\{\(\) => remove\(r\.site\)\}/);
  // the server answers a Remove with what the line names, and keeps the kind for the line's minutes only
  const { announceRemoved, showsRemoved, clearRemoved, removedLine } = await import("../src/removed.js");
  const r = announceRemoved({ did: 7, title: "portal.example", kind: "signin" });
  assert.ok(showsRemoved(r, ["signin"])); assert.ok(!showsRemoved(r, ["task"])); assert.equal(removedLine(r.title, r.verb), "Removed portal.example");
  clearRemoved(7);
  const rd = fs.readFileSync(new URL("../../taskuary/recentlydeleted.py", import.meta.url), "utf8");
  assert.match(rd, /^SHORT = \('connection', 'signout', 'cli', 'signin'\)/m);
  assert.match(fs.readFileSync(new URL("../../taskuary/server.py", import.meta.url), "utf8"), /out = signin\.remove\(store, site, ACTOR\)\r?\n\s+if not out: raise HTTPException\(404/);
});
