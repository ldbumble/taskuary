// NO CLOSE OUT ANYWHERE (the owner, 2026-11-06: "why does this task still have close out? i thought we removed this from everywhere? ... there
// should no longer be close out code anywhere"). Every task is Came from and its one chat; the draft's Send, the emails owed, the landing,
// the hand-off and the close are cards in the chat. So no string the app shows says "Close out" - a comment may tell the history, a word on
// the screen may not - and the words the server and the Assistant read (words.json, buttons.json, stages.json) say the chat too.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url)), src = path.join(here, "..", "src"), pkg = path.join(here, "..", "..", "taskuary");
// ...a word with a space or a hyphen is shown; an identifier or an API path (closeoutOf, /closeout - the GitHub finish) is wiring
const CLOSE_OUT = /\bclose[ -]out\b/i;
// ...what is left of a source once its comments are gone: block comments (JSX's {/* */} too) and line comments - never a "//" inside a URL
const code = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "").split("\n").map((l) => l.replace(/(^|[^:"'`\\])\/\/.*$/, "$1")).join("\n");

test("no string the app shows says Close out", () => {
  const hits = [];
  for (const f of fs.readdirSync(src).filter((f) => /\.(jsx?|mjs)$/.test(f)))
    code(fs.readFileSync(path.join(src, f), "utf8")).split("\n").forEach((l, i) => { if (CLOSE_OUT.test(l)) hits.push(`${f}:${i + 1}: ${l.trim().slice(0, 140)}`); });
  assert.deepEqual(hits, [], hits.join("\n"));
});

test("the words the server, the phone and the Assistant read say the chat, never Close out", () => {
  for (const f of ["words.json", "buttons.json", "stages.json"]) {
    const j = JSON.parse(fs.readFileSync(path.join(pkg, f), "utf8"));
    const said = JSON.stringify(j, (k, v) => (k === "_" ? undefined : v));    // ...its own history notes ("_") aside
    assert.doesNotMatch(said, CLOSE_OUT, f);
  }
});

test("the page has no Close out section, column, tab or stage left", () => {
  const page = fs.readFileSync(path.join(src, "TaskPage.jsx"), "utf8"), layout = fs.readFileSync(path.join(src, "taskLayout.js"), "utf8");
  assert.doesNotMatch(code(page), /slot\("close"|"close" \}|SECTIONS\[2\]|closeBody|closeOutRef|data-tq-closeout|EarlierRounds|AgentDraftNotice|CARDS_IN_SUMMARY/);
  assert.doesNotMatch(code(layout), /closeStatus|closeOut|closeHolds|CLOSE_BY_HAND|taskSections|chatHome|advisorAt|sectionHere|key: "close"/);
  for (const gone of ["CloseoutRounds.jsx", "closeoutRounds.js", "AgentDraftNotice.jsx"]) assert.ok(!fs.existsSync(path.join(src, gone)), gone);
});
