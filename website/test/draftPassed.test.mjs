import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { draftHome, draftPassed, placeCards, rowOf } from "../src/agentSummary.js";

/* A DRAFT IS OLD NEWS THE MOMENT THE OWNER PROMPTS (the owner, 2026-11-10: "i asked it to rewrite a email, it reqrote in place then put it under the
   prompt. Check that this does not happen? ... The second you write ptompt on email action it should go gray and then it should generate new
   email action box under it with new email.."). Driven in a browser first (browser/cards-in-their-turn): a reply drafted on arrival stood at the
   chat's foot, so his line went OVER it and the card jumped under his line; then, stale, it vanished, and the new card came alone. */
const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const mail = { id: "came-in-1", role: "user", createdAt: "2026-11-10 08:00:00", metadata: { custom: { brief: true, mail: [{}] } } };
const draft = { ReviewId: 1, TaskId: 1, Kind: "draft_reply", Status: "pending", DraftText: "Hi Erin, a long review.", CreatedAt: "2026-11-10 08:01:00" };
const line = { id: "m2", role: "user", createdAt: new Date(Date.now()), content: [{ type: "text", text: "make it shorter" }] };

test("a draft no turn wrote stands under the row it came after, by time - never at the foot under a line typed later", () => {
  assert.equal(rowOf([mail, line], "2026-11-10 08:01:00"), "came-in-1");
  assert.equal(draftHome([draft], [mail]), "came-in-1");
  assert.equal(draftHome([draft], [mail, line]), "came-in-1", "his line after it does not carry it down");
  // ...a turn the server named holds its own draft
  assert.equal(draftHome([{ ...draft, turn: "a7" }], [mail, { id: "a7", role: "assistant", createdAt: "2026-11-10 08:05:00" }, line]), "a7");
  assert.equal(draftHome([], [mail]), null);
  // ...and the NEW draft, written while the turn his line began is at work (drawn before its answer is filed, no time of its own yet), is that
  // turn's - under his line it stood over the turn's head, then jumped down into the turn (the recorded walk, 2026-11-10)
  const at = { id: "live-1", role: "assistant" }, mine = { ...line, createdAt: "2026-11-10 09:00:00" };
  assert.equal(draftHome([{ ...draft, ReviewId: 2, CreatedAt: "2026-11-10 09:00:05" }], [mail, mine, at]), "live-1");
  // ...and the moment that turn's answer is filed - stamped when it ENDED, after the draft - before the server names it the draft's turn: still
  // that turn's. Read by its stamp, the card stood a beat under his line, over the answer's head, then jumped into it (the recorded walk, 2026-11-10)
  const done = { id: "a9", role: "assistant", createdAt: "2026-11-10 09:00:09" };
  assert.equal(draftHome([{ ...draft, ReviewId: 2, CreatedAt: "2026-11-10 09:00:05" }], [mail, mine, done]), "a9");
  // ...while a draft from before his line stays under the mail when his line's answer is filed
  assert.equal(draftHome([draft], [mail, mine, done]), "came-in-1");
});

test("the draft is passed from the paint his line is drawn in - his own line in the thread, or one held on the page", () => {
  assert.equal(draftPassed([draft], [mail]), false, "T0: live");
  assert.equal(draftPassed([draft], [mail, line]), true, "his line in the thread, as the runtime draws it at the press");
  assert.equal(draftPassed([draft], [mail], Date.now()), true, "a line held on the page");
  assert.equal(draftPassed([{ ...draft, stale: true }], [mail]), true, "the server says a line came after it");
  // ...Taskuary's own lines are not his: a brief, a press, the mail that came in
  assert.equal(draftPassed([draft], [mail, { ...line, metadata: { custom: { brief: true } } }, { ...line, id: "p", metadata: { custom: { press: true } } }]), false);
  // ...an email the task owes (a slot's card) the same as a reply
  assert.equal(draftPassed([{ ...draft, Kind: "slot" }], [mail, line]), true);
  // ...and the NEW draft, written after his line, is live
  assert.equal(draftPassed([{ ...draft, ReviewId: 2, CreatedAt: new Date(Date.now() + 5000).toISOString() }], [mail, line]), false);
});

test("a replaced draft's record stands where the draft stood: by its time, under the mail, never under the newest turn", () => {
  const msgs = [mail, line, { id: "a1", role: "assistant", createdAt: new Date(Date.now() + 9000) }];
  const [c] = placeCards([{ key: "replaced:1", at: draft.CreatedAt, rid: 1, byRow: true }], msgs, {});
  assert.equal(c.after, "came-in-1");
});

test("the page greys a passed draft where it stands and draws every row's cards, the mail's too", () => {
  const gw = src("GeneralWorkspace.jsx"), rd = src("ReviewDecision.jsx");
  assert.match(rd, /const off = busy \|\| drafting \|\| passed;/);
  assert.match(rd, /const passed = React\.useContext\(PassedCtx\);/);
  assert.ok(!/replanning/.test(src("TaskPage.jsx").match(/<ReviewDecision review=\{pendingReview\}[^\n]*\n[^\n]*\n[^\n]*/)[0]), "no turn-long greying of whatever draft waits");
  assert.match(gw, /<RowCards id=\{line\} \/>/);
  assert.ok(!gw.includes("<StaleDrafts"), "no second, read-only copy of the draft under its turn");
});
