// ONE BUTTON PER JOB (the owner, 2026-10-02): "Save result" was Stop and save for an ended session, "Send this result
// to someone" was Hand it to a person once an agent had reported, and a close-out's "Not yet" was Next or Remind me.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("no Stop and save on the task page, live or ended - the x on the running turn stops an agent", () => {
  const page = read("TaskPage.jsx");
  assert.doesNotMatch(page, /Save result/);
  // the owner, 2026-11-10: "no need for stop and save button"
  assert.doesNotMatch(page, /"save-end"/);
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
