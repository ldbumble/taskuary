// A REMOVE ACTS AT ONCE, AND UNDO TAKES IT BACK (the owner, 2026-10-21: no "are you sure"). Remove, Sign out, Disconnect and Not ours
// each asked first; now each runs on the press and leaves "Removed <it> - Undo" in place, and Recently deleted keeps a report, a
// workflow, a rule and a profile for 30 days (recentlydeleted.py). The one exception is a connection card's Remove, which asks once
// (the owner, 2026-11-05: one press, one confirm) - connectorUses.test.mjs pins its question.
import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { announceRemoved, clearRemoved, fromAnswer, lastRemoved, onRemoved, removedLine, showsRemoved, UNDO_MS } from "../src/removed.js";
import { followUps } from "../src/proposalCard.js";

const SRC = new URL("../src/", import.meta.url);
const read = (f) => readFileSync(new URL(f, SRC), "utf8");

test("no page asks before it removes but a connection card: no confirm dialog and no browser confirm box anywhere else", () => {
  const bad = [];
  for (const f of readdirSync(SRC).filter((f) => /\.(jsx?|mjs)$/.test(f) && f !== "ui.jsx")) {
    const s = read(f);
    const asks = (s.match(/<ConfirmDelete\b/g) || []).length;
    const allowed = f === "ConnectorsView.jsx" && asks === 1 && /function RemoveConnection\([\s\S]*?<ConfirmDelete open=\{asking\}/.test(s);
    if (asks && !allowed) bad.push(`${f}: <ConfirmDelete>`);
    if (/window\.confirm\(/.test(s)) bad.push(`${f}: window.confirm`);
  }
  assert.deepEqual(bad, []);
  // ...and the sign-outs, which asked in the app's own <Confirm>
  assert.doesNotMatch(read("ConnectorsView.jsx"), /title="Sign out of (ChatGPT|Microsoft)\?"/);
});

test("one verb: Remove - the buttons that said Delete say Remove", () => {
  assert.match(read("ReportsView.jsx"), /Remove \{workflow \? "routine" : "report"}/);
  assert.match(read("WorkflowEditor.jsx"), />Remove routine</);
  assert.match(read("AgentsPanel.jsx"), />Remove<\/Button>/);
  assert.match(read("SettingsView.jsx"), /title="Remove this rule"/);
  assert.doesNotMatch(read("ReportsView.jsx") + read("WorkflowEditor.jsx"), /Delete (workflow|routine|report)/);
});

test("the Undo line: announced by the press, drawn by the list that holds its kind, and only while it is fresh", () => {
  const seen = [];
  const off = onRemoved((r) => seen.push(r));
  const r = announceRemoved({ did: 7, title: "Outlook mail", kind: "connection" });
  assert.equal(removedLine(r.title, r.verb), "Removed Outlook mail");
  assert.equal(removedLine("ChatGPT", "Signed out of"), "Signed out of ChatGPT");
  assert.equal(lastRemoved().did, 7);
  assert.equal(showsRemoved(r, ["connection"]), true);
  assert.equal(showsRemoved(r, ["report"]), false);
  assert.equal(showsRemoved(r, ["connection"], r.at + UNDO_MS + 1), false);
  clearRemoved(7);
  assert.equal(lastRemoved(), null);
  off();
  assert.equal(seen.length, 2);
  // the server's answer names the kind it filed it under: a report and a workflow are told apart there
  assert.deepEqual(fromAnswer({ deleted: 3, title: "AP ageing", kind: "workflow" }, "report"), { did: 3, title: "AP ageing", kind: "workflow" });
});

// ...and leaving a card loses nothing: every field saves itself, so what was still waiting to save goes as the card closes
// (the owner, 2026-11-05) - a draft kept for later, with a bar to save it from, is gone with the Save bar
test("leaving a card saves what was still waiting to save - nothing asks, nothing is kept unsaved", () => {
  const d = read("ConnectorDraft.jsx");
  assert.match(d, /useEffect\(\(\) => \(\) => \{ if \(timer\.current\) save\(\); \}, \[save\]\);/);
  assert.match(d, /if \(s \|\| Object\.keys\(cfgPatch\(b, c\)\)\.length\) post\(true\);/);
  assert.doesNotMatch(d, /keptDraft/);
});

test("Not ours runs as just this once, and offers From now on after it - never before", () => {
  const p = { verb: "not_ours", kind: "message.file", target: 12, params: { learn: false }, alts: [{ verb: "not_ours", label: "Just this once", current: true },
    { verb: "not_ours_sender", label: "From now on - their mail is filed for you" }, { verb: "block_sender", label: "A rule in Settings" }] };
  // its own operation on the same message: filed, the item is off the pile and cannot be looked up there again
  assert.deepEqual(followUps(p, { status: "done" }), [{ verb: "not_ours_sender", label: "From now on - their mail is filed for you",
    follow: { kind: "preference.exclude_sender", target: 12, params: { scope: "sender" } } }]);
  assert.deepEqual(followUps(p, { status: "error" }), []);
  assert.deepEqual(followUps({ ...p, verb: "close" }, { status: "done" }), []);
  // the card no longer prints the switch behind just-this-once
  assert.match(read("proposalCard.js"), /"wrap", "learn"\]/);
});
