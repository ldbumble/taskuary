// ONE BUTTON PER JOB (the owner, 2026-10-02): "Save result" was Save and end session for an ended session, "Send this result
// to someone" was Hand it to a person once an agent had reported, and a close-out's "Not yet" was Next or Remind me.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("the write-up is Save and end session, live or ended, and only one of them is ever offered", () => {
  const page = read("TaskPage.jsx");
  assert.doesNotMatch(page, /Save result/);
  assert.equal((page.match(/\{ id: "save-end"/g) || []).length, 2);   // live (agent group) or ended (More) - never both
  assert.match(page, /\.\.\.\(liveSession \? \[/);
  assert.match(page, /\.\.\.\(!liveSession && canSave && agentBar \? \[\{ id: "save-end", group: "more", label: "Save and end session"/);
});

test("a finished agent's result is sent on by Hand it to a person", () => {
  const page = read("TaskPage.jsx");
  assert.doesNotMatch(page, /Send this result to someone|send-result/);
  assert.match(page, /title: report \? "Forwards it to a person with the agent's result in it/);
});

test("a close-out offers Remind me, never Not yet", () => {
  const dec = read("ReviewDecision.jsx"), rp = read("reviewProposal.js");
  assert.doesNotMatch(rp, /"Not yet"/);
  assert.match(dec, /\{ id: no\("remind"\), label: "Remind me", tone: "q", disabled: busy, run: onRemind, title: remindTitle \}/);
  assert.match(dec, /\(co \|\| proposal\?\.kind === "closeout"\) && onRemind && <Button[^\n]*>Remind me<\/Button>/);
});
