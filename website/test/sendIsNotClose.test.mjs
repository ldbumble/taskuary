// SENDING AND CLOSING ARE TWO STEPS (the owner, 2026-10-18): the button under a draft is Send and it only sends; Approve runs only the
// agent's act; Mark done is the one close. A send leaves the item on the table with its receipt - Mark done and Next on its row.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { hint, label } from "../src/buttons.js";
import { sentChips } from "../src/funnelPile.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
// capabilities.js imports the page's api client; its pure rules are lifted from the source and run here
const caps = (() => {
  const c = read("capabilities.js"), grab = (n) => c.slice(c.indexOf(`export const ${n} =`), c.indexOf("\n};", c.indexOf(`export const ${n} =`)) + 3);
  const one = (n) => c.split("\n").find((l) => l.startsWith(`export const ${n} =`));
  const src = [one("canSend"), one("channelCanSend"), grab("draftCanSend")].join("\n").replace(/export const /g, "const ");
  return new Function(`${src}\nreturn { canSend, channelCanSend, draftCanSend };`)();
})();

test("Send only sends and Approve only runs - each says the task stays open until Mark done", () => {
  assert.equal(label("approve"), "Send");
  assert.match(hint("approve"), /stays open until you Mark done/);
  assert.equal(label("approve", "action"), "Approve");
  assert.match(hint("approve", "action"), /^Runs only what the agent proposes/);
  assert.equal(label("close"), "Mark done");
  const all = JSON.stringify(JSON.parse(readFileSync(new URL("../../taskuary/buttons.json", import.meta.url), "utf8")).verbs);
  assert.doesNotMatch(all, /Send & close|no_close/);
});

test("a send's receipt offers Mark done only where there is a task, and Next always", () => {
  assert.deepEqual(sentChips(12, "TQ-12").chips.map((c) => [c.verb, c.label, c.tid ?? null]), [["close", "Mark done", 12], ["next", "Next", null]]);
  assert.deepEqual(sentChips(null).chips.map((c) => c.verb), ["next"], "no task, no Mark done");
});

test("the canvas keeps a sent item on the table: the card folds, the receipt carries the ways on, nothing settles", () => {
  const cards = read("assistantCards.jsx"), view = read("AssistantView.jsx");
  assert.match(cards, /if \(ran && onSent\) onSent\(said, card\.tid, card\.ref\);\n\s+else onDone\?\.\(said\);/);
  assert.doesNotMatch(cards, /and closes the task/);
  assert.match(cards, /the task stays open until you \$\{btn\("close"\)\}/);
  const sent = view.slice(view.indexOf("const sent = (receipt"), view.indexOf("\n  };", view.indexOf("const sent = (receipt")));
  assert.match(sent, /role: "receipt", text: receipt, \.\.\.sentChips\(tid, ref\)/);
  assert.doesNotMatch(sent, /funnel\/settle|advance\(/, "a send neither settles the item nor walks on");
  assert.match(view, /reply: <ReplyCard card=\{c\} onDone=\{actions\.done\} onSent=\{actions\.sent\}/);
  // Mark done under the receipt closes the task it names - the item may be gone with its draft - then the walk goes on
  assert.match(view, /if \(c\.verb === "close" && c\.tid\) \{[\s\S]{0,200}runOperation\(api, "task\.complete", c\.tid\)[\s\S]{0,200}advance\(null, true\)/);
  // ...and an Approve run from a proposal takes the server's own chips for its receipt (concierge.sent_chips)
  assert.match(view, /\(out\.status !== "done" \|\| p\.kind === "review\.approve"\) && res\?\.chips\?\.length/);
});

test("no screen says a send closes the task", () => {
  for (const f of ["ReviewDecision.jsx", "assistantCards.jsx", "TaskPage.jsx", "NewSheet.jsx"]) {
    const s = read(f);
    assert.doesNotMatch(s, /Send & close|Copy & close|Sending it closes the task|approving (it|them) closes the task|send and close out/, f);
  }
  assert.match(read("ReviewDecision.jsx"), /`\$\{sendWord\} sends this to \$\{replyContext\(r\)\} - \$\{stays\}\.`/);
});

test("whether a draft can leave is asked of capabilities.js, with the row's own CanSend kept for what it knows more", () => {
  const live = { known: true, send: { teams: false, email: true } };
  assert.equal(caps.draftCanSend(live, { Channel: "email", CanSend: true }), true);
  assert.equal(caps.draftCanSend(live, { Channel: "teams", CanSend: true }), false, "the channel's live answer");
  assert.equal(caps.draftCanSend(live, { Channel: "email", CanSend: false }), false, "the row knows the draft has nobody to go to");
  assert.equal(caps.draftCanSend(live, { Channel: "teams", Deliver: JSON.stringify({ kind: "zoho_invoice" }) }), true, "an invoice asks no channel");
  assert.equal(caps.draftCanSend(live, null), false);
  assert.equal(caps.channelCanSend({ known: false, send: {} }, "teams", false), false, "the row's word until the answer is in");
  assert.equal(caps.channelCanSend(live, "teams", true), false, "the live answer once it is");
  assert.equal(caps.channelCanSend(live, "email", false), true);
  assert.match(read("ReviewDecision.jsx"), /const canSendIt = draftCanSend\(caps, r\);/);
  assert.doesNotMatch(read("ReviewDecision.jsx"), /r\.CanSend [!=]==/);
  assert.match(read("GeneralWorkspace.jsx"), /\{!draftCanSend\(caps, review\) \? null : \(/);
  assert.doesNotMatch(read("assistantCards.jsx"), /CanSend [!=]== false/);
});

test("the dead-end walk takes a failed send's fix by its own words: an id ending ':fix' is a named button", () => {
  const d = readFileSync(new URL("../deadend_check.mjs", import.meta.url), "utf8");
  const line = d.split("\n").find((l) => l.startsWith("const named = "));
  const named = new Function("NAMED", `${line.replace("const named = ", "return ")}`)(new Set(["Send", "Next"]));
  assert.equal(named("Connect a mailbox", "12:fix"), true);
  assert.equal(named("Connect a mailbox", "12:approve"), false);
  assert.equal(named("Connect a coding tool", "chat:go"), true);
  assert.equal(named("Connect a coding tool", "chat:3:go"), true);
  assert.equal(named("Send", ""), true);
  assert.match(d, /id: b\.getAttribute\("data-tq-verb"\) \|\| ""/);
  assert.match(d, /s\.verbs\.filter\(\(v\) => !named\(v\.word, v\.id\)\)/);
});
