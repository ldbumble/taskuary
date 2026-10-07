// REPLY OPENS AT ONCE (the owner, 2026-10-01: "Reply opens at once with "Drafting…" and the draft fills in - never waits on
// the AI"). Every Reply press asked the server to write the draft before it answered, so the card came up only when the model
// was done - a blank wait of however long the model took. The box opens now (`later`), and the draft is asked for behind it.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { draftJob, openReply, subscribeDrafts } from "../src/replyDraft.js";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const fakeApi = (draft) => {
  const calls = [];
  let release;
  const held = new Promise((r) => { release = r; });
  return { calls, release, post: async (url, body) => {
    calls.push([url, body]);
    if (url.includes("/messages/")) return { data: { reviewId: 41, taskId: 7, draft: "", drafting: true } };
    await held;
    if (draft instanceof Error) throw Object.assign(draft, { response: { data: { detail: draft.message } } });
    return { data: { ok: true, draft } };
  } };
};

test("the box opens before the model answers, says Drafting, and fills in when it does", async () => {
  const api = fakeApi("Yes, Tuesday works.");
  let woke = 0; const off = subscribeDrafts(() => { woke += 1; });
  const opened = await openReply(api, 9, "say yes");
  assert.equal(opened.reviewId, 41, "the card can be drawn now");
  assert.deepEqual(api.calls[0], ["/api/messages/9/reply", { draft: true, later: true, instruction: "say yes" }]);
  assert.deepEqual(api.calls[1], ["/api/reviews/41/draft", { instruction: "say yes" }], "the draft is asked for behind it, with the owner's words");
  assert.equal(draftJob(41).state, "drafting");
  api.release(); await draftJob(41).promise;
  assert.deepEqual([draftJob(41).state, draftJob(41).draft], ["done", "Yes, Tuesday works."]);
  assert.ok(woke >= 2, "the card hears both");
  off();
});

test("a draft that fails says why in the card", async () => {
  const api = fakeApi(new Error("no AI connector is set up to write replies"));
  await openReply(api, 10);
  api.release(); await draftJob(41).promise;
  assert.equal(draftJob(41).state, "failed");
  assert.match(draftJob(41).error, /no AI connector/);
});

test("the Game's Reply presses open at once too, and its draft box says Drafting until the draft lands", () => {
  const game = read("gameItem.jsx");
  assert.doesNotMatch(game, /\/reply`, \{ draft: true, instruction: null \}/, "no Game press waits on the model for a fresh draft");
  assert.equal((game.match(/openReply\(api, item\.mid\)/g) || []).length, 3, "Draft a reply, Reply from this, the reply chip");
  const draft = game.slice(game.indexOf("function Draft("), game.indexOf("export function Moves("));
  assert.match(draft, /useDraftJob\(item\.rid\)/);
  assert.match(draft, /drafting \? "Drafting…"/);
});

test("every Reply press opens at once, and both views of a draft show Drafting while it is written", () => {
  const cards = read("assistantCards.jsx"), view = read("AssistantView.jsx"), page = read("TaskPage.jsx"), dec = read("ReviewDecision.jsx");
  assert.doesNotMatch(cards, /\/reply`, \{ draft: true/, "no card waits on the model");
  assert.equal((cards.match(/openReply\(api, /g) || []).length, 2, "Draft a reply, an fyi's Reply");
  assert.match(view, /if \(verb === "reply" && mid\) \{\n\s+const data = await openReply\(api, mid, d\.text \|\| null\);/);
  assert.match(page, /await \(generate \? draftReply\(api, replyMessage\.MessageId\)/);   // the import, renamed: the page's own openReply shadowed it
  for (const src of [cards, dec]) assert.match(src, /useDraftJob\(/);
  assert.match(dec, /drafting \? "Drafting…"/);
  assert.match(cards.slice(cards.indexOf("export function ReplyCard"), cards.indexOf("export function MeetingCard")), /drafting \? "Drafting…"/);
});
