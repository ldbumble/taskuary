// HIS EDIT IS WHAT GOES (the owner, 2026-11-26: "never even overwrite an edit of a text for any card from user ... They would send email with
// generated email instead of their edits"). What he typed into a card is held by its review alone - not by where the card is drawn, and not
// by the words it was typed over - kept on the server as he types, read back after a reload, and it is what the press carries from any
// screen. The page's half of tests/test_his_edit_is_what_goes.py. Invented people.
import test from "node:test";
import assert from "node:assert/strict";
import { flushEdit, heldEdit, hisText, holdEdit, keepEdits, onHeld, savedEdit, seedEdit, unsaved } from "../src/heldEdits.js";
import { actionFor, asLeft, pressOf, stateOf, textKey, valuesOf } from "../src/actionCard.js";
import { editAfterRefile, heldWords } from "../src/replyDraft.js";
import { press } from "../src/press.js";

const FILED = "We built a scheduler. It is good at finding a time.";
const HIS = "Have you ever tried to get nine people into one room?\n\nWe built a scheduler that finds the best time and shows what it costs.\n\nAlex Doyle";
const post = (text = FILED) => ({ action: "run_tool", type: "linkedin_post", connector_id: 4, text, visibility: "PUBLIC", image: "tour.mp4" });

test("a post's press carries the words in its box, after the card is drawn again and after another draft is filed under it", () => {
  const act = actionFor("linkedin_post"), p = post(), tk = textKey(act);
  holdEdit(701, { text: HIS });
  // ...the card set down under a later turn is a new component: it opens on what its review holds (ActReview's useState(kept?.text ?? p[tk]))
  const remount = (row) => seedEdit(row.ReviewId, row.OwnerEdit)?.text ?? String(row.post[tk] || "");
  assert.equal(remount({ ReviewId: 701, post: p }), HIS, "drawn again: his words");
  assert.equal(remount({ ReviewId: 701, post: post("A new draft, written again.") }), HIS, "other words filed under it: still his");
  assert.equal(remount({ ReviewId: 701, post: p, DraftText: JSON.stringify(p) }), HIS, "the same review handed over by another list: still his");
  const body = pressOf("approve", act, p, remount({ ReviewId: 701, post: p }), valuesOf(act, p));
  assert.equal(body.final_text, HIS, "the press sends them");
  assert.deepEqual(body.shown, p, "against the proposal the card was drawn from");
  assert.equal("fields" in body, false, "and no pick he did not move");
  assert.equal(pressOf("reject", act, p, HIS, valuesOf(act, p)).final_text, null, "his no carries no words");
  assert.deepEqual(pressOf("approve", act, p, HIS, { ...valuesOf(act, p), visibility: "CONNECTIONS" }).fields, { visibility: "CONNECTIONS" }, "a pick he moved goes with it");
});

test("the card his press failed on reads what he pressed, never the words its agent wrote", () => {
  const act = actionFor("linkedin_post"), p = post();
  assert.equal(asLeft(act, p, HIS, valuesOf(act, p)).text, HIS, "at once, from what he pressed");
  // ...and from the row once it comes back: the failed review keeps the proposal as he pressed it (verdicts: its FinalText)
  const row = { ReviewId: 702, Status: "superseded", ActError: "LinkedIn returned 400", post: { ...p, text: HIS } };
  assert.deepEqual(stateOf(row), { done: false, failed: true, said: "" });
  assert.equal(row.post[textKey(act)], HIS);
});

test("what he typed is kept on the server as he types, and is there before any press on the card", async () => {
  const saved = [], posted = [];
  keepEdits(async (id, edit) => { saved.push([id, edit && { ...edit }]); });
  holdEdit(703, { text: "Have you" }); holdEdit(703, { text: HIS });
  assert.equal(unsaved(703), true, "typing: not saved at every keystroke");
  // ...a press with no words of its own (the rail's, a list's one press) - his are on the server first, so they are what it sends
  const api = { post: async (url, body) => { posted.push([url, body, saved.length]); return { data: { ok: true, status: "approved" } }; } };
  const out = await press(api, 703, { verb: "approve" });
  assert.equal(out.kind, "ok");
  assert.deepEqual(saved, [[703, { text: HIS }]], "saved once, as he left it");
  assert.deepEqual(posted, [["/api/reviews/703/decide", { final_text: null, note: null, verb: "approve" }, 1]], "and saved BEFORE the press went");
  assert.equal(unsaved(703), false);
  holdEdit(703, { text: null }); await flushEdit(703);
  assert.deepEqual(saved[1], [703, null], "taken back: the server is told that too");
  assert.equal(await savedEdit(704), undefined, "a card he never typed into saves nothing");
  keepEdits(null);
});

test("after a reload the card reads back what the server kept, once, and his taking it back is never undone by an older row", () => {
  const row = { ReviewId: 705, DraftText: FILED, OwnerEdit: JSON.stringify({ text: HIS, cc: ["gail@northwind.example"] }) };
  assert.equal(hisText(row), HIS, "a reload, a restart, another screen: his words");
  assert.deepEqual(heldEdit(705).cc, ["gail@northwind.example"], "and whom he copied");
  holdEdit(705, { text: null, cc: null });
  assert.equal(hisText(row), null, "he took it back; the row read before that was saved does not bring it back");
  assert.equal(hisText({ ReviewId: 706, DraftText: FILED }), null, "a card as filed has none");
  assert.equal(hisText({ ReviewId: 707, OwnerEdit: "{not json" }), null);
});

test("two cards drawn on one review read the same words", () => {
  const heardBy = [], off = onHeld((id) => heardBy.push([id, heldEdit(id)?.text]));
  holdEdit(708, { text: HIS }); off();
  assert.deepEqual(heardBy, [[708, HIS]]);
});

test("a draft filed under a reply's open box never replaces words he typed - only his own ask for other words does", () => {
  const typed = "Thanks Gail - Thursday at 2 works for me.";
  // ...the thread moved and the refreshed draft is shown beside his; the server holds his words (OwnerEdit); a keystroke not saved yet
  for (const keep of [true]) assert.equal(editAfterRefile({ text: typed, keep }), typed);
  assert.equal(heldWords(JSON.stringify({ text: typed })), typed);
  assert.equal(heldWords(null), "");
  assert.equal(heldWords({ cc: ["gail@northwind.example"] }), "");
  // ...his own Redraft, or a rewrite he asked the Assistant for: the server took his words back, and the new draft shows
  assert.equal(editAfterRefile({ text: typed, keep: false }), null);
  assert.equal(editAfterRefile({ text: "", keep: true }), null, "an emptied box holds no words");
});
