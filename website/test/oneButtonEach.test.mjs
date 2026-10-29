// ONE BUTTON PER JOB (the owner, 2026-10-02): "Save result" was Stop and save for an ended session, "Send this result
// to someone" was Hand it to a person once an agent had reported, and a close-out's "Not yet" was Next or Remind me.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("the write-up is Stop and save, offered once, and only while the session is live", () => {
  const page = read("TaskPage.jsx");
  assert.doesNotMatch(page, /Save result/);
  // an ended session (failed, finished, cut off by a restart) has nothing to stop (owner-approved, 2026-10-20)
  assert.equal((page.match(/\{ id: "save-end"/g) || []).length, 1);
  assert.match(page, /\.\.\.\(liveSession \? \[/);
});

test("a finished agent's result is sent on by Hand it to a person", () => {
  const page = read("TaskPage.jsx");
  assert.doesNotMatch(page, /Send this result to someone|send-result/);
  assert.match(page, /\{ id: "hand", group: "more", label: labelOfRow\("hand"\)/);
});

test("a close-out offers Remind me, never Not yet", () => {
  const dec = read("ReviewDecision.jsx"), rp = read("reviewProposal.js");
  assert.doesNotMatch(rp, /"Not yet"/);
  assert.match(dec, /\{ id: no\("remind"\), label: btn\("defer"\), tone: "q", disabled: off, run: onRemind, title: remindTitle \}/);
  assert.match(dec, /\(co \|\| proposal\?\.kind === "closeout"\) && onRemind && <Button[^\n]*>\{btn\("defer"\)\}<\/Button>/);
});
